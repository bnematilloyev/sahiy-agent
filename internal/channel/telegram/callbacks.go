package telegram

import (
	"context"
	"strconv"
	"strings"

	"github.com/go-telegram/bot"
	"github.com/go-telegram/bot/models"

	appcatalog "github.com/sahiy-backend/sahiy-agent/internal/app/catalog"
	"github.com/sahiy-backend/sahiy-agent/internal/app/chat"
	apppickup "github.com/sahiy-backend/sahiy-agent/internal/app/pickup"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/pickup"
)

// CallbackServices are optional handlers for inline Telegram callbacks.
type CallbackServices struct {
	Pickup        *apppickup.Service
	Category      *appcatalog.CategoryService
	ProductSearch *appcatalog.ProductSearchService
}

var orderMenuQueries = map[string]string{
	"all":       "buyurtmalarim holati",
	"active":    "aktiv buyurtmalarim",
	"daigou":    "xitoydagi daigou buyurtmalarim",
	"delivery":  "yetkazib berish buyurtmalarim",
	"unpicked":  "olib ketilmagan buyurtmalarim",
	"cancelled": "bekor qilingan buyurtmalarim",
	"dashboard": "filialdagi buyurtmalarim",
	"completed": "yakunlangan buyurtmalarim",
}

func (b *Bot) handlePickupCallback(ctx context.Context, tgBot *bot.Bot, update *models.Update) {
	if b.callbacks.Pickup == nil {
		return
	}
	q := update.CallbackQuery
	msg := callbackMessage(q)
	if q == nil || msg == nil {
		return
	}
	kind, value, ok := pickup.ParseCallback(q.Data)
	if !ok {
		return
	}
	_, _ = tgBot.AnswerCallbackQuery(ctx, &bot.AnswerCallbackQueryParams{CallbackQueryID: q.ID})

	lang := b.langFor(q.From.ID, "")
	res, err := b.callbacks.Pickup.RespondCallback(ctx, kind, value, lang)
	if err != nil {
		b.log.Error("telegram: pickup callback", "error", err)
		return
	}
	_, _ = tgBot.EditMessageText(ctx, &bot.EditMessageTextParams{
		ChatID:      msg.Chat.ID,
		MessageID:   msg.ID,
		Text:        res.Text,
		ReplyMarkup: inlineMarkupFromExtra(res.ChannelExtra),
	})
}

func (b *Bot) handleCategoryCallback(ctx context.Context, tgBot *bot.Bot, update *models.Update) {
	if b.callbacks.Category == nil {
		return
	}
	q := update.CallbackQuery
	msg := callbackMessage(q)
	if q == nil || msg == nil {
		return
	}
	categoryID, ok := parseCategoryCallback(q.Data)
	if !ok {
		return
	}
	_, _ = tgBot.AnswerCallbackQuery(ctx, &bot.AnswerCallbackQueryParams{CallbackQueryID: q.ID})

	lang := b.langFor(q.From.ID, "")
	res, err := b.callbacks.Category.RespondOpen(ctx, categoryID, lang)
	if err != nil {
		b.log.Error("telegram: category callback", "error", err)
		return
	}
	_, _ = tgBot.EditMessageText(ctx, &bot.EditMessageTextParams{
		ChatID:      msg.Chat.ID,
		MessageID:   msg.ID,
		Text:        res.Text,
		ReplyMarkup: inlineMarkupFromExtra(res.ChannelExtra),
	})

	if res.ChannelExtra == nil && b.callbacks.ProductSearch != nil {
		keyword, err := b.callbacks.Category.CategorySearchKeyword(ctx, categoryID)
		if err != nil || keyword == "" {
			return
		}
		searchRes, err := b.callbacks.ProductSearch.Respond(ctx, keyword, lang)
		if err != nil {
			return
		}
		payload := PayloadFromExtra(searchRes.Text, searchRes.ChannelExtra)
		b.deliverRichContent(ctx, tgBot, msg.Chat.ID, lang, payload)
	}
}

func (b *Bot) handleOrderMenuCallback(ctx context.Context, tgBot *bot.Bot, update *models.Update) {
	q := update.CallbackQuery
	msg := callbackMessage(q)
	if q == nil || msg == nil {
		return
	}
	code, ok := parseOrderMenuCallback(q.Data)
	if !ok {
		return
	}
	query, ok := orderMenuQueries[code]
	if !ok {
		return
	}
	_, _ = tgBot.AnswerCallbackQuery(ctx, &bot.AnswerCallbackQueryParams{CallbackQueryID: q.ID})

	userID := q.From.ID
	lang := b.langFor(userID, "")
	state := b.users.Get(userID)
	meta := map[string]any{
		"channel":        channelName,
		"reply_language": langHint(lang),
	}
	if state.VerifiedPhone != "" {
		meta["verified_phone"] = state.VerifiedPhone
	}
	if state.SahiyUserID > 0 {
		meta["sahiy_user_id"] = state.SahiyUserID
	}

	cmd := chat.ReplyCommand{UserID: formatUserID(userID), Text: query, Channel: channelName, Metadata: meta}
	if sid := state.SessionID; sid != "" {
		cmd.SessionID = sid
	}
	reply, err := b.chat.Reply(ctx, cmd)
	if err != nil {
		b.log.Error("telegram: order menu callback", "error", err)
		return
	}
	state.SessionID = reply.SessionID.String()
	payload := PayloadFromExtra(reply.Text, reply.ChannelExtra)
	b.msgr.SendText(ctx, tgBot, msg.Chat.ID, payload.Text, inlineMarkupFromExtra(reply.ChannelExtra))
	b.deliverRichContent(ctx, tgBot, msg.Chat.ID, lang, payload)
}

func parseCategoryCallback(data string) (int64, bool) {
	if !strings.HasPrefix(data, "ct_o_") {
		return 0, false
	}
	parts := strings.Split(data, "_")
	if len(parts) < 3 {
		return 0, false
	}
	id, err := strconv.ParseInt(parts[2], 10, 64)
	return id, err == nil && id > 0
}

func parseOrderMenuCallback(data string) (string, bool) {
	if !strings.HasPrefix(data, "ord_") {
		return "", false
	}
	code := strings.TrimPrefix(data, "ord_")
	return code, code != ""
}
