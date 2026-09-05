package telegram

import (
	"context"
	"io"
	"log/slog"
	"testing"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/config"
)

func testBot(cfg config.Telegram) *Bot {
	return &Bot{
		cfg: cfg,
		log: slog.New(slog.NewTextHandler(io.Discard, nil)),
	}
}

// The core of graceful shutdown: a reply already being composed must not be
// killed the instant SIGTERM arrives, or the customer is left with nothing.
func TestHandlerContextSurvivesShutdownSignal(t *testing.T) {
	pollCtx, stop := context.WithCancel(context.Background())
	base, cancelHandlers := newHandlerBase(pollCtx)
	defer cancelHandlers()

	b := testBot(config.Telegram{HandlerTimeout: time.Minute})
	b.handlerBase = base

	handlerCtx, cancel := b.handlerContext()
	defer cancel()

	stop() // shutdown signal arrives while the handler is running

	select {
	case <-handlerCtx.Done():
		t.Fatal("handler context was cancelled by the shutdown signal")
	case <-time.After(50 * time.Millisecond):
	}
}

// The detached context must still be bounded, or a wedged provider call would
// hold a worker slot forever.
func TestHandlerContextIsAlwaysTimeBounded(t *testing.T) {
	b := testBot(config.Telegram{HandlerTimeout: 30 * time.Second})
	b.handlerBase = context.Background()

	ctx, cancel := b.handlerContext()
	defer cancel()

	if _, ok := ctx.Deadline(); !ok {
		t.Fatal("handler context has no deadline")
	}
}

// A missing or nonsensical timeout must not disable the bound.
func TestHandlerContextFallsBackToDefaultTimeout(t *testing.T) {
	b := testBot(config.Telegram{HandlerTimeout: 0})
	b.handlerBase = context.Background()

	ctx, cancel := b.handlerContext()
	defer cancel()

	deadline, ok := ctx.Deadline()
	if !ok {
		t.Fatal("handler context has no deadline")
	}
	if remaining := time.Until(deadline); remaining > defaultHandlerTimeout+time.Second {
		t.Errorf("remaining = %v, want the default bound of %v", remaining, defaultHandlerTimeout)
	}
}

// Handlers invoked outside Run (tests, direct calls) must not panic on a nil base.
func TestHandlerContextWithoutRun(t *testing.T) {
	b := testBot(config.Telegram{HandlerTimeout: time.Second})

	ctx, cancel := b.handlerContext()
	defer cancel()

	if ctx == nil {
		t.Fatal("handler context is nil")
	}
}

// The grace period is a bound, not a promise: whatever is still running when it
// expires gets cancelled so the process can exit.
func TestDrainCancelsHandlersAfterGrace(t *testing.T) {
	pollCtx, stop := context.WithCancel(context.Background())
	base, cancelHandlers := newHandlerBase(pollCtx)
	defer cancelHandlers()

	b := testBot(config.Telegram{ShutdownGrace: 30 * time.Millisecond})
	go b.drainOnShutdown(pollCtx, base, cancelHandlers)

	stop()

	select {
	case <-base.Done():
	case <-time.After(2 * time.Second):
		t.Fatal("in-flight handlers were never cancelled after the grace period")
	}
}

// Grace disabled means stop immediately rather than never.
func TestDrainWithoutGraceCancelsImmediately(t *testing.T) {
	pollCtx, stop := context.WithCancel(context.Background())
	base, cancelHandlers := newHandlerBase(pollCtx)
	defer cancelHandlers()

	b := testBot(config.Telegram{ShutdownGrace: 0})
	go b.drainOnShutdown(pollCtx, base, cancelHandlers)

	stop()

	select {
	case <-base.Done():
	case <-time.After(2 * time.Second):
		t.Fatal("handlers were not cancelled with grace disabled")
	}
}

// The drain goroutine must exit when the bot shuts down cleanly, rather than
// linger until the grace timer fires.
func TestDrainExitsWhenHandlersFinishFirst(t *testing.T) {
	pollCtx, stop := context.WithCancel(context.Background())
	base, cancelHandlers := newHandlerBase(pollCtx)

	b := testBot(config.Telegram{ShutdownGrace: time.Hour})
	done := make(chan struct{})
	go func() {
		b.drainOnShutdown(pollCtx, base, cancelHandlers)
		close(done)
	}()

	stop()
	cancelHandlers() // Run finished and released the handler base

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("drain goroutine did not exit after handlers were released")
	}
}
