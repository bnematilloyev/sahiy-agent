package telegram

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"runtime/debug"
	"strings"
	"time"

	"github.com/go-telegram/bot"
	"github.com/go-telegram/bot/models"

	"github.com/sahiy-backend/sahiy-agent/internal/app/chat"
	"github.com/sahiy-backend/sahiy-agent/internal/config"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

const channelName = "telegram"

// defaultWorkers is used when TELEGRAM_WORKERS is unset or invalid.
const defaultWorkers = 32

// defaultHandlerTimeout bounds one update when TELEGRAM_HANDLER_TIMEOUT_SECONDS
// is unset or invalid.
const defaultHandlerTimeout = 120 * time.Second

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
	workers   int

	tg *bot.Bot
	// handlerBase is the parent of every handler context. Set by Run before the
	// worker goroutines exist, then only read.
	handlerBase context.Context
	cancel      context.CancelFunc
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
		streams:   NewStreamConfig(cfg),
		users:     NewUserStore(),
		rating:    NewRatingScheduler(cfg.RatingInactivity),
	}
	// Updates are handled concurrently: a single worker would serialize every
	// customer behind the slowest LLM call. Per-user state is guarded by
	// UserStore, and the chat pipeline keeps no cross-request state.
	b.workers = cfg.Workers
	if b.workers <= 0 {
		b.workers = defaultWorkers
	}
	opts := []bot.Option{
		bot.WithDefaultHandler(b.handleDefault),
		bot.WithWorkers(b.workers),
		// Order matters: recoverPanics is outermost so it also catches a panic
		// raised while setting up the handler context.
		bot.WithMiddlewares(recoverPanics(log), b.withHandlerContext),
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

// Run starts long polling and blocks until ctx is cancelled and every in-flight
// reply has finished (or the shutdown grace period expires).
//
// A cancelled ctx is the normal way to stop, so Run reports success: returning
// context.Canceled would make the process exit non-zero and read as a crash to
// systemd or Docker.
func (b *Bot) Run(ctx context.Context) error {
	pollCtx, cancelPolling := context.WithCancel(ctx)
	b.cancel = cancelPolling
	defer cancelPolling()

	// Handler contexts hang off a base that shutdown does NOT cancel
	// immediately, so a reply already being composed gets to finish and reach
	// the customer. Written before Start spawns the workers that read it.
	handlerBase, cancelHandlers := newHandlerBase(ctx)
	b.handlerBase = handlerBase
	defer cancelHandlers()

	go b.drainOnShutdown(pollCtx, handlerBase, cancelHandlers)

	b.log.Info("telegram bot starting", "workers", b.workers, "handler_timeout", b.cfg.HandlerTimeout)
	// Start blocks until polling stops and every worker has returned from the
	// handler it was running, which is what makes the drain effective.
	b.tg.Start(pollCtx)
	b.log.Info("telegram bot stopped cleanly")
	return nil
}

// newHandlerBase builds the parent of every handler context. It deliberately
// drops ctx's cancellation (keeping its values) so a shutdown signal does not
// instantly abort replies that are mid-flight; the drain decides when to cancel.
func newHandlerBase(ctx context.Context) (context.Context, context.CancelFunc) {
	return context.WithCancel(context.WithoutCancel(ctx))
}

// drainOnShutdown gives in-flight replies a bounded window to finish once the
// shutdown signal arrives, then cancels whatever is still running.
func (b *Bot) drainOnShutdown(pollCtx, handlerBase context.Context, cancelHandlers context.CancelFunc) {
	<-pollCtx.Done()

	grace := b.cfg.ShutdownGrace
	if grace <= 0 {
		cancelHandlers()
		return
	}

	b.log.Info("telegram: shutdown signal, draining in-flight replies", "grace", grace)
	timer := time.NewTimer(grace)
	defer timer.Stop()
	select {
	case <-timer.C:
		b.log.Warn("telegram: drain grace expired, cancelling in-flight replies")
		cancelHandlers()
	case <-handlerBase.Done():
		// Run already returned and cleaned up.
	}
}

// handlerContext derives the context for one update: detached from shutdown
// cancellation (so the drain can do its job) but always time-bounded.
func (b *Bot) handlerContext() (context.Context, context.CancelFunc) {
	base := b.handlerBase
	if base == nil {
		// Run was never called (tests invoking handlers directly).
		base = context.Background()
	}
	timeout := b.cfg.HandlerTimeout
	if timeout <= 0 {
		timeout = defaultHandlerTimeout
	}
	return context.WithTimeout(base, timeout)
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

// recoverPanics keeps one malformed update from killing the whole bot process.
// The customer gets no reply for that message, which is bad but recoverable;
// a crashed process is not.
func recoverPanics(log *slog.Logger) bot.Middleware {
	return func(next bot.HandlerFunc) bot.HandlerFunc {
		return func(ctx context.Context, tgBot *bot.Bot, update *models.Update) {
			defer func() {
				if rec := recover(); rec != nil {
					log.Error("telegram: panic recovered",
						"panic", rec,
						"update_id", updateID(update),
						"stack", string(debug.Stack()),
					)
				}
			}()
			next(ctx, tgBot, update)
		}
	}
}

// withHandlerContext replaces the polling context with a per-update one, so a
// shutdown does not abort a reply mid-composition and no single update can
// occupy a worker slot indefinitely.
func (b *Bot) withHandlerContext(next bot.HandlerFunc) bot.HandlerFunc {
	return func(_ context.Context, tgBot *bot.Bot, update *models.Update) {
		ctx, cancel := b.handlerContext()
		defer cancel()
		next(ctx, tgBot, update)
	}
}

func updateID(update *models.Update) int64 {
	if update == nil {
		return 0
	}
	return update.ID
}

// goSafe runs fn on its own goroutine with panic recovery. Background goroutines
// are not covered by the bot middleware, and an unrecovered panic on any
// goroutine takes down the entire process.
func (b *Bot) goSafe(name string, fn func()) {
	go func() {
		defer func() {
			if rec := recover(); rec != nil {
				b.log.Error("telegram: panic recovered in background task",
					"task", name, "panic", rec, "stack", string(debug.Stack()))
			}
		}()
		fn()
	}()
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

	state := b.users.Snapshot(userID)
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
	state := b.users.Snapshot(userID)
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

	b.users.SetVerifiedPhone(userID, phone, sahiyUID)
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

	if b.users.TakeAwaitingProductSearch(userID) && len([]rune(text)) < 2 {
		// Too short to search: re-arm the prompt and ask again.
		b.users.AwaitProductSearch(userID)
		b.msgr.SendText(ctx, tgBot, update.Message.Chat.ID, T(ProductSearchTooShort, lang), mainMenuKeyboard(lang))
		return
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
		b.users.AwaitProductSearch(update.Message.From.ID)
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

	// A failed write must not cost the customer their thank-you: the rating is
	// already given, and telling them it failed helps nobody.
	if err := b.chat.RecordRating(ctx, formatUserID(userID), channelName, stars); err != nil {
		b.log.Error("telegram: could not record rating", "error", err, "user_id", userID, "stars", stars)
	}

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
	state := b.users.Snapshot(userID)

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

	b.users.SetSessionID(userID, reply.SessionID.String())
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

func (b *Bot) buildMetadata(update *models.Update, state UserState, lang shared.Language) map[string]any {
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
	if l := b.users.Snapshot(userID).Language; l.Code() != "" {
		return l
	}
	lang, _ := shared.DetectReplyLanguage(text)
	return lang
}

func (b *Bot) startTyping(ctx context.Context, tgBot *bot.Bot, chatID int64) func() {
	interval := b.cfg.TypingInterval
	if interval <= 0 {
		interval = 4 * time.Second
	}
	stop := make(chan struct{})
	b.goSafe("typing", func() {
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
	})
	return func() { close(stop) }
}

func (b *Bot) sendRatingPrompt(ctx context.Context, tgBot *bot.Bot, userID, chatID int64, lang shared.Language) {
	if !b.users.ClaimRatingPrompt(userID) {
		return
	}
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
