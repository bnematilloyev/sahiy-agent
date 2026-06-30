// Package bootstrap is the shared composition root for HTTP API and Telegram bot
// entrypoints. Both binaries wire the same ReplyService pipeline.
package bootstrap

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sahiy-backend/sahiy-agent/internal/app/chat"
	"github.com/sahiy-backend/sahiy-agent/internal/app/faq"
	appidentity "github.com/sahiy-backend/sahiy-agent/internal/app/identity"
	"github.com/sahiy-backend/sahiy-agent/internal/app/router"
	"github.com/sahiy-backend/sahiy-agent/internal/config"
	"github.com/sahiy-backend/sahiy-agent/internal/infra/embedding"
	"github.com/sahiy-backend/sahiy-agent/internal/infra/llm"
	"github.com/sahiy-backend/sahiy-agent/internal/infra/persistence/postgres"
	"github.com/sahiy-backend/sahiy-agent/internal/platform/eventlog"
	sahiyinfra "github.com/sahiy-backend/sahiy-agent/internal/infra/sahiy"
	"github.com/sahiy-backend/sahiy-agent/internal/channel/telegram"
)

// App holds wired application services shared by all delivery channels.
type App struct {
	Pool         *pgxpool.Pool
	ReplyService *chat.ReplyService
	Callbacks    telegram.CallbackServices
	Log          *slog.Logger
}

// New opens the database, runs migrations, and wires the chat pipeline.
func New(ctx context.Context, cfg *config.Config, log *slog.Logger) (*App, error) {
	pool, err := postgres.Connect(ctx, cfg.DB.URL)
	if err != nil {
		return nil, fmt.Errorf("bootstrap: db connect: %w", err)
	}
	if err := postgres.Migrate(ctx, pool, log); err != nil {
		pool.Close()
		return nil, fmt.Errorf("bootstrap: migrate: %w", err)
	}

	sessions := postgres.NewConversationRepository(pool)
	faqRepo := postgres.NewFAQRepository(pool)
	ticketRepo := postgres.NewTicketRepository(pool)
	publisher := eventlog.New(log)

	completer := llm.NewCompleter(cfg.AI, log)
	embedder := embedding.NewEmbedder(cfg.AI, log)

	faqService := faq.New(faqRepo, embedder, completer, faq.Config{
		Threshold: cfg.AI.RagThreshold,
		TopK:      cfg.AI.RagTopK,
		MaxTokens: cfg.AI.RagMaxTokens,
		MockOnly:  embedder.UsesMockOnly(),
	}, log)
	routerService := router.New(completer, log)

	var stack *sahiyinfra.ServiceStack
	if cfg.Sahiy.HasServiceUser() {
		stack = sahiyinfra.NewServiceStack(cfg.Sahiy, log)
	}

	handlers, callbacks := buildHandlers(cfg, stack, ticketRepo, completer, log)
	responder := chat.NewRouterResponder(routerService, faqService, handlers, cfg.AI.EscalationThreshold, log)

	var identitySvc *appidentity.Service
	if stack != nil {
		identitySvc = appidentity.New(stack.CustomerAPI, log)
	}

	replyService := chat.NewReplyService(sessions, ticketRepo, responder, identitySvc, publisher, cfg.Session.IdleTimeout, log)

	return &App{
		Pool:         pool,
		ReplyService: replyService,
		Callbacks:    callbacks,
		Log:          log,
	}, nil
}

// Close releases database resources.
func (a *App) Close() {
	if a.Pool != nil {
		a.Pool.Close()
	}
}
