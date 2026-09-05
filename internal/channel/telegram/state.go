package telegram

import (
	"context"
	"sync"
	"time"

	"github.com/go-telegram/bot"
	"github.com/go-telegram/bot/models"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// UserState holds per-Telegram-user UI state (not persisted — rebuilt on /start).
//
// It is always handled as a value: the store hands out copies and applies
// mutations under its own lock. Never keep a *UserState across calls - Telegram
// updates and the rating timer run on different goroutines, and a shared
// pointer would let them corrupt each other's session ids and phone markers.
type UserState struct {
	Language              shared.Language
	VerifiedPhone         string
	SahiyUserID           int64
	SessionID             string
	AwaitingProductSearch bool
	RatedThisSession      bool
	RatingPromptSent      bool
}

// HasVerifiedPhone reports whether the user completed phone verification.
func (s UserState) HasVerifiedPhone() bool { return s.VerifiedPhone != "" }

// UserStore is a thread-safe in-memory map of Telegram user IDs to state. All
// access goes through Snapshot (read a copy) or Update (mutate under the lock).
type UserStore struct {
	mu   sync.Mutex
	data map[int64]*UserState
}

// NewUserStore constructs an empty store.
func NewUserStore() *UserStore {
	return &UserStore{data: make(map[int64]*UserState)}
}

// Snapshot returns a copy of the user's state, creating a default entry when the
// user is not known yet. The copy is safe to read without further locking, but
// writing to it has no effect on the store - use Update for that.
func (s *UserStore) Snapshot(userID int64) UserState {
	s.mu.Lock()
	defer s.mu.Unlock()
	return *s.entry(userID)
}

// Update applies mutate to the user's state while holding the store lock and
// returns the resulting snapshot. Read-modify-write sequences must go through
// this method so they stay atomic.
func (s *UserStore) Update(userID int64, mutate func(*UserState)) UserState {
	s.mu.Lock()
	defer s.mu.Unlock()
	st := s.entry(userID)
	mutate(st)
	return *st
}

// entry returns the live state for a user. Callers must hold s.mu.
func (s *UserStore) entry(userID int64) *UserState {
	if st, ok := s.data[userID]; ok {
		return st
	}
	st := &UserState{Language: shared.LangUz}
	s.data[userID] = st
	return st
}

// SetLanguage records the user's chosen reply language.
func (s *UserStore) SetLanguage(userID int64, lang shared.Language) {
	s.Update(userID, func(st *UserState) { st.Language = lang })
}

// SetVerifiedPhone records a verified phone and its Sahiy account id together,
// so no reader can observe one without the other.
func (s *UserStore) SetVerifiedPhone(userID int64, phone string, sahiyUserID int64) {
	s.Update(userID, func(st *UserState) {
		st.VerifiedPhone = phone
		st.SahiyUserID = sahiyUserID
	})
}

// SetSessionID remembers the conversation the user is currently in.
func (s *UserStore) SetSessionID(userID int64, sessionID string) {
	s.Update(userID, func(st *UserState) { st.SessionID = sessionID })
}

// ClearSession forgets the current conversation so the next message opens a new one.
func (s *UserStore) ClearSession(userID int64) {
	s.Update(userID, func(st *UserState) { st.SessionID = "" })
}

// AwaitProductSearch arms the "next message is a product search" flag.
func (s *UserStore) AwaitProductSearch(userID int64) {
	s.Update(userID, func(st *UserState) { st.AwaitingProductSearch = true })
}

// TakeAwaitingProductSearch atomically reads and clears the product-search flag,
// so two concurrent messages cannot both consume the same prompt.
func (s *UserStore) TakeAwaitingProductSearch(userID int64) bool {
	var was bool
	s.Update(userID, func(st *UserState) {
		was = st.AwaitingProductSearch
		st.AwaitingProductSearch = false
	})
	return was
}

// ResetRating clears rating state at the start of a new conversation.
func (s *UserStore) ResetRating(userID int64) {
	s.Update(userID, func(st *UserState) {
		st.RatedThisSession = false
		st.RatingPromptSent = false
	})
}

// MarkRated records that the user rated the conversation.
func (s *UserStore) MarkRated(userID int64) {
	s.Update(userID, func(st *UserState) {
		st.RatedThisSession = true
		st.RatingPromptSent = true
	})
}

// ClaimRatingPrompt atomically reserves the right to send the rating prompt.
// It returns false when the user already rated or a prompt was already sent, so
// concurrent timers cannot ask the same user twice.
func (s *UserStore) ClaimRatingPrompt(userID int64) bool {
	var claimed bool
	s.Update(userID, func(st *UserState) {
		if st.RatedThisSession || st.RatingPromptSent {
			return
		}
		st.RatingPromptSent = true
		claimed = true
	})
	return claimed
}

// RatingScheduler sends a delayed service-rating prompt after inactivity.
type RatingScheduler struct {
	delay time.Duration
	mu    sync.Mutex
	tasks map[int64]context.CancelFunc
}

func NewRatingScheduler(delay time.Duration) *RatingScheduler {
	return &RatingScheduler{delay: delay, tasks: make(map[int64]context.CancelFunc)}
}

func (r *RatingScheduler) Cancel(userID int64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if cancel, ok := r.tasks[userID]; ok {
		cancel()
		delete(r.tasks, userID)
	}
}

func (r *RatingScheduler) Schedule(ctx context.Context, tgBot *bot.Bot, host *Bot, userID, chatID int64, lang shared.Language) {
	if r.delay <= 0 {
		return
	}
	r.Cancel(userID)
	timerCtx, cancel := context.WithCancel(ctx)
	r.mu.Lock()
	r.tasks[userID] = cancel
	r.mu.Unlock()

	host.goSafe("rating-prompt", func() {
		select {
		case <-timerCtx.Done():
			return
		case <-time.After(r.delay):
		}
		host.sendRatingPrompt(timerCtx, tgBot, userID, chatID, lang)
	})
}

func parseRatingCallback(data string) int {
	if len(data) != 6 || data[:5] != "rate_" {
		return 0
	}
	switch data[5] {
	case '1':
		return 1
	case '2':
		return 2
	case '3':
		return 3
	case '4':
		return 4
	case '5':
		return 5
	default:
		return 0
	}
}

func parseLangCallback(data string) shared.Language {
	switch data {
	case "lang_uz":
		return shared.LangUz
	case "lang_ru":
		return shared.LangRu
	case "lang_en":
		return shared.LangEn
	case "lang_zh":
		return shared.LangZh
	default:
		return shared.LangUz
	}
}

func sendTyping(ctx context.Context, tgBot *bot.Bot, chatID int64) error {
	_, err := tgBot.SendChatAction(ctx, &bot.SendChatActionParams{
		ChatID: chatID,
		Action: models.ChatActionTyping,
	})
	return err
}
