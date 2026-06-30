package telegram

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/go-telegram/bot"
	"github.com/go-telegram/bot/models"

	"github.com/sahiy-backend/sahiy-agent/internal/app/chat"
	"github.com/sahiy-backend/sahiy-agent/internal/config"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

const channelName = "telegram"

// Bot is the Telegram long-polling adapter around chat.ReplyService.
type Bot struct {
	cfg       config.Telegram
	log       *slog.Logger
	chat      *chat.ReplyService
	callbacks CallbackServices
	msgr      *Messenger
	streams   *StreamConfig
	users     *UserStore
	rating    *RatingScheduler

	tg     *bot.Bot
	cancel context.CancelFunc
}

// New constructs the Telegram bot. Caller must invoke Run for polling to start.
func New(cfg config.Telegram, reply *chat.ReplyService, callbacks CallbackServices, log *slog.Logger) (*Bot, error) {
	if cfg.BotToken == "" {
		return nil, fmt.Errorf("telegram: TELEGRAM_BOT_TOKEN is required")
	}
	b := &Bot{
		cfg:       cfg,
		log:       log,
		chat:      reply,
		callbacks: callbacks,
		msgr:      NewMessenger(cfg.SendRetries),
		streams: NewStreamConfig(cfg),
		users:   NewUserStore(),
		rating:  NewRatingScheduler(cfg.RatingInactivity),
	}
	opts := []bot.Option{
		bot.WithDefaultHandler(b.handleDefault),
	}
	if cfg.HTTPTimeout > 0 {
		opts = append(opts, bot.WithHTTPClient(time.Minute, &http.Client{Timeout: cfg.HTTPTimeout}))
	}
	tg, err := bot.New(cfg.BotToken, opts...)
	if err != nil {
		return nil, fmt.Errorf("telegram: create bot: %w", err)
	}
	b.tg = tg
	b.registerHandlers()
	return b, nil
}

// Run starts long polling until ctx is cancelled.
func (b *Bot) Run(ctx context.Context) error {
	ctx, b.cancel = context.WithCancel(ctx)
	b.log.Info("telegram bot starting")
	b.tg.Start(ctx)
	<-ctx.Done()
	b.log.Info("telegram bot stopped")
	return ctx.Err()
}

// Stop cancels polling.
func (b *Bot) Stop() {
	if b.cancel != nil {
		b.cancel()
	}
}

func (b *Bot) registerHandlers() {
	b.tg.RegisterHandler(bot.HandlerTypeMessageText, "/start", bot.MatchTypePrefix, b.handleStart)
	b.tg.RegisterHandler(bot.HandlerTypeMessageText, "/new", bot.MatchTypePrefix, b.handleNew)
	b.tg.RegisterHandler(bot.HandlerTypeCallbackQueryData, "lang_", bot.MatchTypePrefix, b.handleLangCallback)
	b.tg.RegisterHandler(bot.HandlerTypeCallbackQueryData, "rate_", bot.MatchTypePrefix, b.handleRatingCallback)
	b.tg.RegisterHandler(bot.HandlerTypeCallbackQueryData, "pp_", bot.MatchTypePrefix, b.handlePickupCallback)
	b.tg.RegisterHandler(bot.HandlerTypeCallbackQueryData, "ct_", bot.MatchTypePrefix, b.handleCategoryCallback)
	b.tg.RegisterHandler(bot.HandlerTypeCallbackQueryData, "ord_", bot.MatchTypePrefix, b.handleOrderMenuCallback)
	b.tg.RegisterHandler(bot.HandlerTypeMessageText, "", bot.MatchTypePrefix, b.handleText)
}

func (b *Bot) handleDefault(ctx context.Context, tgBot *bot.Bot, update *models.Update) {
	if update.Message != nil && update.Message.Contact != nil {
		b.handleContact(ctx, tgBot, update)
	}
}

func (b *Bot) handleStart(ctx context.Context, tgBot *bot.Bot, update *models.Update) {
	if update.Message == nil {
		return
	}
	_, _ = tgBot.SendMessage(ctx, &bot.SendMessageParams{
		ChatID:      update.Message.Chat.ID,
		Text:        T(LanguagePickerPrompt, shared.LangUz),
		ReplyMarkup: languageInlineKeyboard(),
	})
}

func (b *Bot) handleLangCallback(ctx context.Context, tgBot *bot.Bot, update *models.Update) {
	q := update.CallbackQuery
	msg := callbackMessage(q)
	if q == nil || msg == nil {
		return
	}
	lang := parseLangCallback(q.Data)
	_, _ = tgBot.AnswerCallbackQuery(ctx, &bot.AnswerCallbackQueryParams{CallbackQueryID: q.ID})

	userID := q.From.ID
	b.users.SetLanguage(userID, lang)

	welcome := T(Welcome, lang)
	_, _ = tgBot.EditMessageText(ctx, &bot.EditMessageTextParams{
		ChatID:    msg.Chat.ID,
		MessageID: msg.ID,
		Text:      welcome,
	})

	state := b.users.Get(userID)
	if state.HasVerifiedPhone() {
		_, _ = tgBot.SendMessage(ctx, &bot.SendMessageParams{
			ChatID:      msg.Chat.ID,
			Text:        welcome,
			ReplyMarkup: mainMenuKeyboard(lang),
		})
	} else {
		_, _ = tgBot.SendMessage(ctx, &bot.SendMessageParams{
			ChatID:      msg.Chat.ID,
			Text:        T(PhonePrompt, lang),
			ReplyMarkup: phoneRequestKeyboard(lang),
		})
	}
}

func (b *Bot) handleNew(ctx context.Context, tgBot *bot.Bot, update *models.Update) {
	if update.Message == nil || update.Message.From == nil {
		return
	}
	userID := update.Message.From.ID
	lang := b.langFor(userID, update.Message.Text)
	b.users.ResetRating(userID)
	b.rating.Cancel(userID)

	if err := b.chat.ResetSession(ctx, formatUserID(userID), channelName); err != nil {
		b.log.Error("telegram: reset session", "error", err, "user_id", userID)
		b.msgr.SendText(ctx, tgBot, update.Message.Chat.ID, T(ErrRetry, lang), nil)
		return
	}
	b.users.ClearSession(userID)

	body := T(NewChatStarted, lang)
	state := b.users.Get(userID)
	if !state.HasVerifiedPhone() {
		body += "\n\n" + T(PhonePrompt, lang)
	}
	markup := models.ReplyMarkup(mainMenuKeyboard(lang))
	if !state.HasVerifiedPhone() {
		markup = phoneRequestKeyboard(lang)
	}
	b.msgr.SendText(ctx, tgBot, update.Message.Chat.ID, body, markup)
}

func (b *Bot) handleContact(ctx context.Context, tgBot *bot.Bot, update *models.Update) {
	if update.Message == nil || update.Message.Contact == nil || update.Message.From == nil {
		return
	}
	userID := update.Message.From.ID
	lang := b.langFor(userID, "")
	contact := update.Message.Contact

	if contact.UserID != 0 && contact.UserID != userID {
		b.msgr.SendText(ctx, tgBot, update.Message.Chat.ID, T(PhoneWrongContact, lang), phoneRequestKeyboard(lang))
		return
	}

	phone := shared.NormalizePhone(contact.PhoneNumber)
	if phone == "" {
		b.msgr.SendText(ctx, tgBot, update.Message.Chat.ID, T(PhoneWrongContact, lang), phoneRequestKeyboard(lang))
		return
	}

	sahiyUID, errText, err := b.chat.RegisterVerifiedPhone(ctx, formatUserID(userID), channelName, phone, lang)
	if err != nil {
		b.log.Error("telegram: register phone", "error", err, "user_id", userID)
		b.msgr.SendText(ctx, tgBot, update.Message.Chat.ID, T(ErrRetry, lang), phoneRequestKeyboard(lang))
		return
	}
	if errText != "" {
		b.msgr.SendText(ctx, tgBot, update.Message.Chat.ID, errText, phoneRequestKeyboard(lang))
		return
	}

	b.users.SetVerifiedPhone(userID, phone)
	b.users.Get(userID).SahiyUserID = sahiyUID
	b.msgr.SendText(ctx, tgBot, update.Message.Chat.ID, T(PhoneSaved, lang), mainMenuKeyboard(lang))
}

func (b *Bot) handleText(ctx context.Context, tgBot *bot.Bot, update *models.Update) {
	if update.Message == nil || update.Message.From == nil {
		return
	}
	text := strings.TrimSpace(update.Message.Text)
	if text == "" || strings.HasPrefix(text, "/") {
		return
	}

	userID := update.Message.From.ID
	lang := b.langFor(userID, text)
	b.rating.Cancel(userID)

	if action, ok := matchMenuAction(text, lang); ok {
		b.handleMenuAction(ctx, tgBot, update, action, lang)
		return
	}

	state := b.users.Get(userID)
	if state.AwaitingProductSearch {
		state.AwaitingProductSearch = false
		if len([]rune(text)) < 2 {
			state.AwaitingProductSearch = true
			b.msgr.SendText(ctx, tgBot, update.Message.Chat.ID, T(ProductSearchTooShort, lang), mainMenuKeyboard(lang))
			return
		}
	}

	b.processMessage(ctx, tgBot, update, text)
}

func (b *Bot) handleMenuAction(ctx context.Context, tgBot *bot.Bot, update *models.Update, action string, lang shared.Language) {
	chatID := update.Message.Chat.ID
	switch action {
	case "new_chat":
		b.handleNew(ctx, tgBot, update)
	case "language":
		b.msgr.SendText(ctx, tgBot, chatID, T(LanguagePickerPrompt, lang), languageInlineKeyboard())
	case "help":
		b.msgr.SendText(ctx, tgBot, chatID, T(MenuHelp, lang), mainMenuKeyboard(lang))
	case "callback":
		b.processMessage(ctx, tgBot, update, T(MenuCallbackText, lang))
	case "product_search":
		b.users.Get(update.Message.From.ID).AwaitingProductSearch = true
		b.msgr.SendText(ctx, tgBot, chatID, T(ProductSearchPrompt, lang), mainMenuKeyboard(lang))
	}
}

func (b *Bot) handleRatingCallback(ctx context.Context, tgBot *bot.Bot, update *models.Update) {
	q := update.CallbackQuery
	msg := callbackMessage(q)
	if q == nil || msg == nil {
		return
	}
	stars := parseRatingCallback(q.Data)
	if stars == 0 {
		return
	}
	_, _ = tgBot.AnswerCallbackQuery(ctx, &bot.AnswerCallbackQueryParams{CallbackQueryID: q.ID})

	userID := q.From.ID
	lang := b.langFor(userID, "")
	b.users.MarkRated(userID)
	b.rating.Cancel(userID)

	thanks := fmt.Sprintf(T(RatingThanks, lang), stars)
	_, _ = tgBot.EditMessageText(ctx, &bot.EditMessageTextParams{
		ChatID:    msg.Chat.ID,
		MessageID: msg.ID,
		Text:      thanks,
	})
}

func (b *Bot) processMessage(ctx context.Context, tgBot *bot.Bot, update *models.Update, text string) {
	if update.Message == nil || update.Message.From == nil {
		return
	}
	userID := update.Message.From.ID
	chatID := update.Message.Chat.ID
	lang := b.langFor(userID, text)
	state := b.users.Get(userID)

	meta := b.buildMetadata(update, state, lang)
	cmd := chat.ReplyCommand{
		UserID:   formatUserID(userID),
		Text:     text,
		Channel:  channelName,
		Metadata: meta,
	}
	if sid := state.SessionID; sid != "" {
		cmd.SessionID = sid
	}

	stopTyping := b.startTyping(ctx, tgBot, chatID)
	defer stopTyping()

	var sentMsg *models.Message
	if b.streams.Enabled {
		sentMsg = b.msgr.SendText(ctx, tgBot, chatID, streamPlaceholder, nil)
	}

	reply, err := b.chat.Reply(ctx, cmd)
	if err != nil {
		b.log.Error("telegram: reply failed", "error", err, "user_id", userID)
		fallback := T(FallbackError, lang)
		if sentMsg != nil {
			b.msgr.EditText(ctx, tgBot, chatID, sentMsg.ID, fallback, mainMenuKeyboard(lang))
		} else {
			b.msgr.SendText(ctx, tgBot, chatID, fallback, mainMenuKeyboard(lang))
		}
		return
	}

	state.SessionID = reply.SessionID.String()
	payload := PayloadFromExtra(reply.Text, reply.ChannelExtra)
	if payload.DisableStream && sentMsg != nil {
		// Product/category replies: replace placeholder with header + cards.
		b.msgr.EditText(ctx, tgBot, chatID, sentMsg.ID, payload.Text, payload.ReplyMarkup)
		b.deliverRichContent(ctx, tgBot, chatID, lang, payload)
	} else {
		b.DeliverReply(ctx, tgBot, chatID, lang, payload, sentMsg)
	}

	b.rating.Schedule(ctx, tgBot, b, userID, chatID, lang)
}

func (b *Bot) buildMetadata(update *models.Update, state *UserState, lang shared.Language) map[string]any {
	meta := map[string]any{
		"channel":        channelName,
		"reply_language": langHint(lang),
	}
	if update.Message != nil {
		meta["telegram_chat_id"] = update.Message.Chat.ID
	}
	if update.Message != nil && update.Message.From != nil && update.Message.From.Username != "" {
		meta["telegram_username"] = update.Message.From.Username
	}
	if state.VerifiedPhone != "" {
		meta["verified_phone"] = state.VerifiedPhone
	}
	if state.SahiyUserID > 0 {
		meta["sahiy_user_id"] = state.SahiyUserID
	}
	return meta
}

func (b *Bot) langFor(userID int64, text string) shared.Language {
	if l := b.users.Get(userID).Language; l.Code() != "" {
		return l
	}
	return shared.DetectLanguage(text)
}

func (b *Bot) startTyping(ctx context.Context, tgBot *bot.Bot, chatID int64) func() {
	interval := b.cfg.TypingInterval
	if interval <= 0 {
		interval = 4 * time.Second
	}
	stop := make(chan struct{})
	go func() {
		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		_ = sendTyping(ctx, tgBot, chatID)
		for {
			select {
			case <-stop:
				return
			case <-ticker.C:
				_ = sendTyping(ctx, tgBot, chatID)
			}
		}
	}()
	return func() { close(stop) }
}

func (b *Bot) sendRatingPrompt(ctx context.Context, tgBot *bot.Bot, userID, chatID int64, lang shared.Language) {
	state := b.users.Get(userID)
	if state.RatedThisSession || state.RatingPromptSent {
		return
	}
	state.RatingPromptSent = true
	b.msgr.SendText(ctx, tgBot, chatID, T(RatingPrompt, lang), ratingInlineKeyboard())
}

func callbackMessage(q *models.CallbackQuery) *models.Message {
	if q == nil || q.Message.Type != models.MaybeInaccessibleMessageTypeMessage {
		return nil
	}
	return q.Message.Message
}

func formatUserID(id int64) string {
	return fmt.Sprintf("%d", id)
}

func langHint(l shared.Language) string {
	switch l.Code() {
	case shared.LangCyr.Code():
		return "uz_cyrl"
	case shared.LangRu.Code():
		return "ru"
	case shared.LangEn.Code():
		return "en"
	case shared.LangZh.Code():
		return "zh"
	default:
		return "uz_lat"
	}
}

// UserStore returns the in-memory user state store (for tests).
func (b *Bot) UserStore() *UserStore { return b.users }
