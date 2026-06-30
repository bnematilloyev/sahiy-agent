// Command bot runs the Sahiy Telegram bot (long polling).
package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/sahiy-backend/sahiy-agent/internal/channel/telegram"
	"github.com/sahiy-backend/sahiy-agent/internal/config"
	"github.com/sahiy-backend/sahiy-agent/internal/platform/bootstrap"
	"github.com/sahiy-backend/sahiy-agent/internal/platform/logger"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "fatal:", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := config.Load()
	if err != nil {
		return fmt.Errorf("load config: %w", err)
	}
	if cfg.Telegram.BotToken == "" {
		return fmt.Errorf("TELEGRAM_BOT_TOKEN is required")
	}

	log := logger.New(cfg.App.LogLevel, cfg.App.LogJSON)
	log.Info("starting sahiy-agent telegram bot", "env", cfg.App.Env, "ai_provider", cfg.AI.Provider)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	app, err := bootstrap.New(ctx, cfg, log)
	if err != nil {
		return err
	}
	defer app.Close()

	tgBot, err := telegram.New(cfg.Telegram, app.ReplyService, app.Callbacks, log)
	if err != nil {
		return err
	}

	return tgBot.Run(ctx)
}
