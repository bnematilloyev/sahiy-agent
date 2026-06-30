package telegram

import (
	"context"
	"fmt"
	"strings"

	"github.com/go-telegram/bot"
	"github.com/go-telegram/bot/models"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/channel"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// ReplyPayload is the Telegram-specific view of a chat reply.
type ReplyPayload struct {
	Text                       string
	ReplyMarkup                models.ReplyMarkup
	PhotoURLs                  []string
	FollowUpMessages           []string
	ProductSearchItems         []map[string]any
	ProductSearchCNYToUZS      float64
	ProductSearchSeeAllKeyword string
	ProductSearchSeeAllURL     string
	DisableStream              bool
}

// PayloadFromExtra maps channel_extra into a Telegram delivery payload.
func PayloadFromExtra(text string, extra map[string]any) ReplyPayload {
	p := ReplyPayload{Text: text}
	if extra == nil {
		return p
	}
	p.ReplyMarkup = inlineMarkupFromExtra(extra)
	if photos, ok := extra[channel.KeyMediaPhotos].([]any); ok {
		for _, raw := range photos {
			if s, ok := raw.(string); ok && s != "" {
				p.PhotoURLs = append(p.PhotoURLs, s)
			}
		}
	}
	if msgs, ok := extra[channel.KeyTelegramMessages].([]any); ok {
		for _, raw := range msgs {
			if s := strings.TrimSpace(fmt.Sprint(raw)); s != "" {
				p.FollowUpMessages = append(p.FollowUpMessages, s)
			}
		}
	}
	if items, ok := extra[channel.KeyProductSearchItems].([]map[string]any); ok {
		p.ProductSearchItems = items
	} else if items, ok := extra[channel.KeyProductSearchItems].([]any); ok {
		for _, raw := range items {
			if m, ok := raw.(map[string]any); ok {
				p.ProductSearchItems = append(p.ProductSearchItems, m)
			}
		}
	}
	if rate, ok := extra[channel.KeyProductSearchCNYToUZS].(float64); ok {
		p.ProductSearchCNYToUZS = rate
	}
	if kw, ok := extra[channel.KeyProductSearchSeeAllKeyword].(string); ok {
		p.ProductSearchSeeAllKeyword = kw
	}
	if url, ok := extra["product_search_see_all_url"].(string); ok {
		p.ProductSearchSeeAllURL = url
	}
	p.DisableStream = channel.DisableStream(extra)
	return p
}

func inlineMarkupFromExtra(extra map[string]any) models.ReplyMarkup {
	raw, ok := extra[channel.KeyInlineKeyboard].([]any)
	if !ok || len(raw) == 0 {
		return nil
	}
	var rows [][]models.InlineKeyboardButton
	for _, rowAny := range raw {
		rowSlice, ok := rowAny.([]any)
		if !ok {
			continue
		}
		var row []models.InlineKeyboardButton
		for _, btnAny := range rowSlice {
			m, ok := btnAny.(map[string]any)
			if !ok {
				if sm, ok := btnAny.(map[string]string); ok {
					m = map[string]any{"text": sm["text"], "callback_data": sm["callback_data"], "url": sm["url"]}
				} else {
					continue
				}
			}
			text := fmt.Sprint(m["text"])
			btn := models.InlineKeyboardButton{Text: text}
			if url, ok := m["url"].(string); ok && url != "" {
				btn.URL = url
			} else if data, ok := m["callback_data"].(string); ok {
				btn.CallbackData = data
			}
			row = append(row, btn)
		}
		if len(row) > 0 {
			rows = append(rows, row)
		}
	}
	if len(rows) == 0 {
		return nil
	}
	return &models.InlineKeyboardMarkup{InlineKeyboard: rows}
}

// DeliverReply sends the main text and any rich attachments for a message update.
func (b *Bot) DeliverReply(ctx context.Context, tgBot *bot.Bot, chatID int64, lang shared.Language, payload ReplyPayload, streamMsg *models.Message) {
	menu := mainMenuKeyboard(lang)
	markup := payload.ReplyMarkup
	if markup == nil {
		markup = menu
	}

	text := payload.Text
	if text == "" {
		text = T(FallbackError, lang)
	}

	if streamMsg != nil {
		b.msgr.EditText(ctx, tgBot, chatID, streamMsg.ID, text, markup)
	} else {
		b.msgr.SendText(ctx, tgBot, chatID, text, markup)
	}

	b.deliverRichContent(ctx, tgBot, chatID, lang, payload)
}

func (b *Bot) deliverRichContent(ctx context.Context, tgBot *bot.Bot, chatID int64, lang shared.Language, payload ReplyPayload) {
	rate := payload.ProductSearchCNYToUZS
	for i, item := range payload.ProductSearchItems {
		pic, _ := item["pic_url"].(string)
		if pic == "" {
			continue
		}
		caption := formatProductCaption(item, lang, rate, i+1)
		buyMarkup := productBuyMarkup(item, lang)
		b.msgr.SendPhoto(ctx, tgBot, chatID, pic, caption, buyMarkup)
	}
	if payload.ProductSearchSeeAllURL != "" || payload.ProductSearchSeeAllKeyword != "" {
		seeAll := seeAllMarkup(payload, lang)
		if seeAll != nil {
			b.msgr.SendText(ctx, tgBot, chatID, "👇", seeAll)
		}
	}
	for _, msg := range payload.FollowUpMessages {
		b.msgr.SendText(ctx, tgBot, chatID, msg, mainMenuKeyboard(lang))
	}
	for _, url := range payload.PhotoURLs {
		if url != "" {
			b.msgr.SendPhoto(ctx, tgBot, chatID, url, "", nil)
		}
	}
}

func productBuyMarkup(item map[string]any, lang shared.Language) models.ReplyMarkup {
	url, _ := item["detail_url"].(string)
	if url == "" {
		return nil
	}
	label := buyLabel(lang)
	return &models.InlineKeyboardMarkup{
		InlineKeyboard: [][]models.InlineKeyboardButton{
			{{Text: label, URL: url}},
		},
	}
}

func seeAllMarkup(payload ReplyPayload, lang shared.Language) models.ReplyMarkup {
	url := payload.ProductSearchSeeAllURL
	if url == "" {
		return nil
	}
	return &models.InlineKeyboardMarkup{
		InlineKeyboard: [][]models.InlineKeyboardButton{
			{{Text: seeAllLabel(lang), URL: url}},
		},
	}
}

func seeAllLabel(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "📋 Смотреть все"
	case shared.LangEn.Code():
		return "📋 See all results"
	default:
		return "📋 Hammasini ko'rish"
	}
}
