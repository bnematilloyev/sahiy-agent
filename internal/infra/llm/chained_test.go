package llm

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"testing"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
)

// stubCompleter returns a fixed completion without any network call.
type stubCompleter struct{ out ai.Completion }

func (s stubCompleter) Complete(context.Context, ai.CompletionRequest) (ai.Completion, error) {
	return s.out, nil
}
func (s stubCompleter) Available() bool { return true }

// captureRecorder records what the chain hands it.
type captureRecorder struct {
	got  chan ai.UsageRecord
	once bool
}

func newCaptureRecorder() *captureRecorder {
	return &captureRecorder{got: make(chan ai.UsageRecord, 4)}
}

func (r *captureRecorder) RecordUsage(_ context.Context, rec ai.UsageRecord) {
	r.got <- rec
}

func (r *captureRecorder) await(t *testing.T) ai.UsageRecord {
	t.Helper()
	select {
	case rec := <-r.got:
		return rec
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for usage record")
		return ai.UsageRecord{}
	}
}

func discardLog() *slog.Logger { return slog.New(slog.NewTextHandler(io.Discard, nil)) }

func TestChainedClientRecordsSessionIDFromContext(t *testing.T) {
	rec := newCaptureRecorder()
	chain := NewChainedClient(NewRulesClient(), rec, 0, discardLog())
	chain.Add("anthropic", stubCompleter{out: ai.Completion{
		Text:  "hi",
		Model: "claude-test",
		Usage: ai.Usage{InputTokens: 10, OutputTokens: 3, CacheReadInputTokens: 7},
	}})

	ctx := ai.WithSessionID(context.Background(), "11111111-2222-3333-4444-555555555555")
	if _, err := chain.Complete(ctx, ai.CompletionRequest{Route: "rag"}); err != nil {
		t.Fatalf("Complete: %v", err)
	}

	got := rec.await(t)
	if got.SessionID != "11111111-2222-3333-4444-555555555555" {
		t.Errorf("SessionID = %q", got.SessionID)
	}
	if got.Route != "rag" || got.Provider != "anthropic" || got.Model != "claude-test" {
		t.Errorf("record context = %+v", got)
	}
	if got.Usage.InputTokens != 10 || got.Usage.CacheReadInputTokens != 7 {
		t.Errorf("Usage = %+v", got.Usage)
	}
}

func TestChainedClientRecordsEmptySessionIDOutsideSession(t *testing.T) {
	rec := newCaptureRecorder()
	chain := NewChainedClient(NewRulesClient(), rec, 0, discardLog())
	chain.Add("anthropic", stubCompleter{out: ai.Completion{Text: "hi", Model: "claude-test"}})

	if _, err := chain.Complete(context.Background(), ai.CompletionRequest{Route: "router"}); err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if got := rec.await(t); got.SessionID != "" {
		t.Errorf("SessionID = %q, want empty for a call outside a session", got.SessionID)
	}
}

// The recorder runs on a detached context so a cancelled request still gets
// its usage written - the tokens were spent either way.
func TestChainedClientRecordsAfterCallerContextCancelled(t *testing.T) {
	rec := newCaptureRecorder()
	chain := NewChainedClient(NewRulesClient(), rec, 0, discardLog())
	chain.Add("anthropic", stubCompleter{out: ai.Completion{Text: "hi", Model: "claude-test"}})

	ctx, cancel := context.WithCancel(ai.WithSessionID(context.Background(), "sess-1"))
	if _, err := chain.Complete(ctx, ai.CompletionRequest{Route: "rag"}); err != nil {
		t.Fatalf("Complete: %v", err)
	}
	cancel()

	if got := rec.await(t); got.SessionID != "sess-1" {
		t.Errorf("SessionID = %q, want sess-1", got.SessionID)
	}
}

// blockingCompleter holds every call until released, so a test can observe how
// many the chain lets run at once.
type blockingCompleter struct {
	entered chan struct{}
	release chan struct{}
}

func (b blockingCompleter) Complete(context.Context, ai.CompletionRequest) (ai.Completion, error) {
	b.entered <- struct{}{}
	<-b.release
	return ai.Completion{Text: "ok", Model: "claude-test"}, nil
}
func (b blockingCompleter) Available() bool { return true }

func TestChainedClientCapsConcurrentProviderCalls(t *testing.T) {
	const limit = 2
	blocker := blockingCompleter{entered: make(chan struct{}, 8), release: make(chan struct{})}
	chain := NewChainedClient(NewRulesClient(), nil, limit, discardLog())
	chain.Add("anthropic", blocker)

	for i := 0; i < 5; i++ {
		go func() { _, _ = chain.Complete(context.Background(), ai.CompletionRequest{}) }()
	}

	// Exactly `limit` calls may be inside the provider at once.
	for i := 0; i < limit; i++ {
		select {
		case <-blocker.entered:
		case <-time.After(2 * time.Second):
			t.Fatalf("only %d of %d calls reached the provider", i, limit)
		}
	}
	select {
	case <-blocker.entered:
		t.Fatalf("a %drd call reached the provider despite the limit of %d", limit+1, limit)
	case <-time.After(100 * time.Millisecond):
	}

	// Releasing one lets exactly one more through.
	blocker.release <- struct{}{}
	select {
	case <-blocker.entered:
	case <-time.After(2 * time.Second):
		t.Fatal("freeing a slot did not admit the next waiting call")
	}
	close(blocker.release)
}

// A caller whose context expires while queued must give up rather than wait
// forever - the request deadline is what sheds load.
func TestChainedClientAcquireRespectsContext(t *testing.T) {
	blocker := blockingCompleter{entered: make(chan struct{}, 4), release: make(chan struct{})}
	chain := NewChainedClient(NewRulesClient(), nil, 1, discardLog())
	chain.Add("anthropic", blocker)

	go func() { _, _ = chain.Complete(context.Background(), ai.CompletionRequest{}) }()
	<-blocker.entered // the single slot is now taken

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	start := time.Now()
	if _, err := chain.Complete(ctx, ai.CompletionRequest{}); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("error = %v, want DeadlineExceeded", err)
	}
	if elapsed := time.Since(start); elapsed > time.Second {
		t.Errorf("waited %v after the deadline; the wait is not context-bound", elapsed)
	}
	close(blocker.release)
}

// A non-positive limit must mean "no limit" rather than deadlocking every call.
func TestChainedClientZeroLimitIsUnlimited(t *testing.T) {
	blocker := blockingCompleter{entered: make(chan struct{}, 8), release: make(chan struct{})}
	chain := NewChainedClient(NewRulesClient(), nil, 0, discardLog())
	chain.Add("anthropic", blocker)

	for i := 0; i < 4; i++ {
		go func() { _, _ = chain.Complete(context.Background(), ai.CompletionRequest{}) }()
	}
	for i := 0; i < 4; i++ {
		select {
		case <-blocker.entered:
		case <-time.After(2 * time.Second):
			t.Fatalf("with no limit all 4 calls should run; only %d did", i)
		}
	}
	close(blocker.release)
}
