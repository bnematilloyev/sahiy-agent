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
type UserState struct {
	Language              shared.Language
	VerifiedPhone         string
	SahiyUserID           int64
	SessionID             string
	AwaitingProductSearch bool
	RatedThisSession      bool
	RatingPromptSent      bool
}

func (s *UserState) HasVerifiedPhone() bool { return s.VerifiedPhone != "" }

// UserStore is a thread-safe in-memory map of Telegram user IDs to state.
type UserStore struct {
	mu   sync.RWMutex
	data map[int64]*UserState
}

func NewUserStore() *UserStore {
	return &UserStore{data: make(map[int64]*UserState)}
}

func (s *UserStore) Get(userID int64) *UserState {
	s.mu.Lock()
	defer s.mu.Unlock()
	if st, ok := s.data[userID]; ok {
		return st
	}
	st := &UserState{Language: shared.LangUz}
	s.data[userID] = st
	return st
}

func (s *UserStore) SetLanguage(userID int64, lang shared.Language) {
	s.Get(userID).Language = lang
}

func (s *UserStore) SetVerifiedPhone(userID int64, phone string) {
	s.Get(userID).VerifiedPhone = phone
}

func (s *UserStore) ClearSession(userID int64) {
	s.Get(userID).SessionID = ""
}

func (s *UserStore) ResetRating(userID int64) {
	st := s.Get(userID)
	st.RatedThisSession = false
	st.RatingPromptSent = false
}

func (s *UserStore) MarkRated(userID int64) {
	st := s.Get(userID)
	st.RatedThisSession = true
	st.RatingPromptSent = true
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

	go func() {
		select {
		case <-timerCtx.Done():
			return
		case <-time.After(r.delay):
		}
		state := host.users.Get(userID)
		if state.RatedThisSession || state.RatingPromptSent {
			return
		}
		host.sendRatingPrompt(timerCtx, tgBot, userID, chatID, lang)
	}()
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
