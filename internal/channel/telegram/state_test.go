package telegram

import (
	"context"
	"io"
	"log/slog"
	"sync"
	"testing"

	"github.com/go-telegram/bot"
	"github.com/go-telegram/bot/models"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// Run with -race: concurrent workers must not corrupt per-user state.
func TestUserStoreConcurrentAccess(t *testing.T) {
	store := NewUserStore()
	const users, iterations = 8, 200

	var wg sync.WaitGroup
	for u := int64(1); u <= users; u++ {
		for _, work := range []func(int64){
			func(id int64) { store.SetSessionID(id, "session") },
			func(id int64) { store.SetVerifiedPhone(id, "+998901112233", id*10) },
			func(id int64) { store.SetLanguage(id, shared.LangRu) },
			func(id int64) { _ = store.Snapshot(id) },
			func(id int64) { _ = store.TakeAwaitingProductSearch(id) },
			func(id int64) { _ = store.ClaimRatingPrompt(id) },
		} {
			wg.Add(1)
			go func(id int64, work func(int64)) {
				defer wg.Done()
				for i := 0; i < iterations; i++ {
					work(id)
				}
			}(u, work)
		}
	}
	wg.Wait()
}

// A snapshot is a copy: writing to it must never leak back into the store.
// This is what made the old pointer-returning API unsafe.
func TestSnapshotIsACopy(t *testing.T) {
	store := NewUserStore()
	store.SetSessionID(1, "original")

	snap := store.Snapshot(1)
	snap.SessionID = "mutated"

	if got := store.Snapshot(1).SessionID; got != "original" {
		t.Errorf("SessionID = %q, want the store to be unaffected by snapshot writes", got)
	}
}

// The phone and its Sahiy account id must become visible together, never one
// without the other - the order lookup trusts both.
func TestSetVerifiedPhoneIsAtomic(t *testing.T) {
	store := NewUserStore()
	store.SetVerifiedPhone(7, "+998901112233", 4242)

	state := store.Snapshot(7)
	if !state.HasVerifiedPhone() || state.SahiyUserID != 4242 {
		t.Errorf("state = %+v, want phone and sahiy id set together", state)
	}
}

// Two concurrent timers must not both prompt the same user for a rating.
func TestClaimRatingPromptGrantsOnce(t *testing.T) {
	store := NewUserStore()

	var mu sync.Mutex
	granted := 0
	var wg sync.WaitGroup
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if store.ClaimRatingPrompt(1) {
				mu.Lock()
				granted++
				mu.Unlock()
			}
		}()
	}
	wg.Wait()

	if granted != 1 {
		t.Errorf("granted = %d, want exactly 1 rating prompt", granted)
	}
}

// A user who already rated is never asked again.
func TestClaimRatingPromptRefusesAfterRating(t *testing.T) {
	store := NewUserStore()
	store.MarkRated(3)

	if store.ClaimRatingPrompt(3) {
		t.Error("ClaimRatingPrompt = true, want false after the user rated")
	}
}

// The product-search prompt is consumed exactly once, so two quick messages
// cannot both be treated as the awaited search query.
func TestTakeAwaitingProductSearchConsumesOnce(t *testing.T) {
	store := NewUserStore()
	store.AwaitProductSearch(5)

	if !store.TakeAwaitingProductSearch(5) {
		t.Fatal("first take = false, want true")
	}
	if store.TakeAwaitingProductSearch(5) {
		t.Error("second take = true, want false")
	}
}

// The go-telegram library does not recover panics itself, so one malformed
// update would otherwise take the bot down for every customer.
func TestRecoverPanicsKeepsBotAlive(t *testing.T) {
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	handler := recoverPanics(log)(func(context.Context, *bot.Bot, *models.Update) {
		panic("bad update")
	})

	defer func() {
		if rec := recover(); rec != nil {
			t.Fatalf("panic escaped the middleware: %v", rec)
		}
	}()
	handler(context.Background(), nil, &models.Update{ID: 42})
}

// A nil update must not turn the recovery path itself into a crash.
func TestRecoverPanicsHandlesNilUpdate(t *testing.T) {
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	handler := recoverPanics(log)(func(context.Context, *bot.Bot, *models.Update) {
		panic("bad update")
	})

	defer func() {
		if rec := recover(); rec != nil {
			t.Fatalf("panic escaped the middleware: %v", rec)
		}
	}()
	handler(context.Background(), nil, nil)
}

func TestRecoverPanicsPassesNormalUpdatesThrough(t *testing.T) {
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	called := false
	handler := recoverPanics(log)(func(context.Context, *bot.Bot, *models.Update) {
		called = true
	})

	handler(context.Background(), nil, &models.Update{ID: 1})

	if !called {
		t.Error("the wrapped handler was not called")
	}
}
