package llm

import (
	"context"
	"errors"
	"log/slog"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
)

// usageRecordTimeout bounds how long a usage-recording write may run in its
// detached background goroutine.
const usageRecordTimeout = 5 * time.Second

// slowAcquireThreshold is how long a call may wait for a concurrency slot
// before the wait is worth logging. Below it, queueing is normal; above it,
// the chain is saturated and somebody should know.
const slowAcquireThreshold = time.Second

// ChainedClient tries a list of real providers in order, falling back to the
// rules client when they all fail (or none are configured). This implements the
// Anthropic -> rules failover chain.
type ChainedClient struct {
	providers []namedCompleter
	fallback  ai.Completer
	recorder  ai.UsageRecorder
	// slots bounds how many provider calls may be in flight at once. A nil
	// channel means unlimited, which is what a non-positive limit configures:
	// a misconfigured zero must not deadlock every request.
	slots chan struct{}
	log   *slog.Logger
}

type namedCompleter struct {
	name      string
	completer ai.Completer
}

// NewChainedClient builds the failover chain. providers should be the real LLM
// adapters in priority order; fallback is the always-available rules client.
// recorder may be nil, in which case token usage is only logged, not persisted.
//
// maxConcurrent caps in-flight provider calls; 0 or less means no cap. The cap
// exists to keep a burst from turning into a wall of provider rate-limit
// errors, which the chain would answer by falling back to rules - a degraded
// reply for every customer at once, which is far worse than waiting.
func NewChainedClient(fallback ai.Completer, recorder ai.UsageRecorder, maxConcurrent int, log *slog.Logger) *ChainedClient {
	c := &ChainedClient{fallback: fallback, recorder: recorder, log: log}
	if maxConcurrent > 0 {
		c.slots = make(chan struct{}, maxConcurrent)
	}
	return c
}

// acquire takes a concurrency slot, waiting for one when the chain is busy.
// The wait is bounded by the caller's context, which already carries the
// request deadline, so a saturated chain sheds load through the same timeout
// that governs everything else rather than through a second one of its own.
func (c *ChainedClient) acquire(ctx context.Context) (release func(), err error) {
	if c.slots == nil {
		return func() {}, nil
	}
	start := time.Now()
	select {
	case c.slots <- struct{}{}:
	case <-ctx.Done():
		c.log.Warn("llm: gave up waiting for a concurrency slot",
			"waited", time.Since(start), "limit", cap(c.slots), "error", ctx.Err())
		return nil, ctx.Err()
	}
	if waited := time.Since(start); waited > slowAcquireThreshold {
		c.log.Warn("llm: waited for a concurrency slot, the chain is saturated",
			"waited", waited, "limit", cap(c.slots))
	}
	return func() { <-c.slots }, nil
}

// Add appends a named real provider to the chain.
func (c *ChainedClient) Add(name string, completer ai.Completer) {
	c.providers = append(c.providers, namedCompleter{name: name, completer: completer})
}

// Available reports whether at least one real provider can serve requests. The
// router uses this to choose between LLM-first and deterministic routing.
func (c *ChainedClient) Available() bool {
	for _, p := range c.providers {
		if p.completer.Available() {
			return true
		}
	}
	return false
}

// Complete tries each available provider in order, then the rules fallback.
// Reaching the fallback means the assistant is running blind, so it is logged at
// error level: it is an operational incident, not a routine miss.
func (c *ChainedClient) Complete(ctx context.Context, req ai.CompletionRequest) (ai.Completion, error) {
	// Only real providers are metered. The rules fallback is local and must
	// stay reachable even when every slot is taken, or an outage plus a burst
	// would leave the customer with no reply at all.
	release, err := c.acquire(ctx)
	if err != nil {
		return ai.Completion{}, err
	}
	defer release()

	var lastErr error
	for _, p := range c.providers {
		if !p.completer.Available() {
			continue
		}
		out, err := p.completer.Complete(ctx, req)
		if err == nil {
			c.log.Info("llm: completion", "provider", p.name, "route", req.Route,
				"session_id", ai.SessionIDFrom(ctx),
				"input_tokens", out.Usage.InputTokens, "output_tokens", out.Usage.OutputTokens,
				"cache_read_tokens", out.Usage.CacheReadInputTokens,
				"cache_creation_tokens", out.Usage.CacheCreationInputTokens)
			c.recordUsage(ctx, p.name, req.Route, out)
			return out, nil
		}
		lastErr = err
		c.log.Warn("llm provider failed, falling back", "provider", p.name, "error", err)
	}
	if c.fallback != nil {
		c.log.Error("llm: all providers unavailable, answering in degraded mode",
			"providers", len(c.providers), "last_error", lastErr)
		return c.fallback.Complete(ctx, req)
	}
	if lastErr == nil {
		lastErr = errors.New("llm: no providers configured")
	}
	return ai.Completion{}, lastErr
}

// recordUsage hands the completion's token accounting to the recorder on a
// detached context, so a slow or failing usage sink never delays the reply
// that already went to the caller. Everything the record needs is read off the
// caller's ctx here, before it is detached.
func (c *ChainedClient) recordUsage(ctx context.Context, provider, route string, out ai.Completion) {
	if c.recorder == nil {
		return
	}
	rec := ai.UsageRecord{
		Provider:  provider,
		Model:     out.Model,
		Route:     route,
		SessionID: ai.SessionIDFrom(ctx),
		Usage:     out.Usage,
	}
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), usageRecordTimeout)
		defer cancel()
		c.recorder.RecordUsage(ctx, rec)
	}()
}
