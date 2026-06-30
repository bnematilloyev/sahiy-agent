package telegram

import (
	"context"
	"time"

	"github.com/go-telegram/bot"
	"github.com/go-telegram/bot/models"

	"github.com/sahiy-backend/sahiy-agent/internal/config"
)

const (
	maxMessageLen   = 4096
	streamPlaceholder = "⏳"
)

// Messenger wraps Telegram send/edit with retries and length clipping.
type Messenger struct {
	retries int
}

func NewMessenger(retries int) *Messenger {
	if retries <= 0 {
		retries = 3
	}
	return &Messenger{retries: retries}
}

func (m *Messenger) SendText(ctx context.Context, tg *bot.Bot, chatID int64, text string, markup models.ReplyMarkup) *models.Message {
	text = clipText(text)
	for attempt := 1; attempt <= m.retries; attempt++ {
		msg, err := tg.SendMessage(ctx, &bot.SendMessageParams{
			ChatID:      chatID,
			Text:        text,
			ReplyMarkup: markup,
		})
		if err == nil {
			return msg
		}
		if attempt < m.retries {
			time.Sleep(time.Duration(attempt) * 1500 * time.Millisecond)
		}
	}
	return nil
}

func (m *Messenger) EditText(ctx context.Context, tg *bot.Bot, chatID int64, messageID int, text string, markup models.ReplyMarkup) {
	text = clipText(text)
	for attempt := 1; attempt <= m.retries; attempt++ {
		_, err := tg.EditMessageText(ctx, &bot.EditMessageTextParams{
			ChatID:      chatID,
			MessageID:   messageID,
			Text:        text,
			ReplyMarkup: markup,
		})
		if err == nil {
			return
		}
		if attempt < m.retries {
			time.Sleep(time.Duration(attempt) * 1500 * time.Millisecond)
		}
	}
}

func (m *Messenger) SendPhoto(ctx context.Context, tg *bot.Bot, chatID int64, photoURL, caption string, markup models.ReplyMarkup) {
	if len(caption) > 1024 {
		caption = caption[:1023] + "…"
	}
	for attempt := 1; attempt <= m.retries; attempt++ {
		_, err := tg.SendPhoto(ctx, &bot.SendPhotoParams{
			ChatID:      chatID,
			Photo:       &models.InputFileString{Data: photoURL},
			Caption:     caption,
			ReplyMarkup: markup,
		})
		if err == nil {
			return
		}
		if attempt < m.retries {
			time.Sleep(time.Duration(attempt) * 1500 * time.Millisecond)
		}
	}
}

func clipText(text string) string {
	if len(text) <= maxMessageLen {
		return text
	}
	return text[:maxMessageLen-1] + "…"
}

// StreamConfig controls placeholder streaming UX.
type StreamConfig struct {
	Enabled bool
}

func NewStreamConfig(cfg config.Telegram) *StreamConfig {
	return &StreamConfig{Enabled: cfg.StreamEnabled}
}
