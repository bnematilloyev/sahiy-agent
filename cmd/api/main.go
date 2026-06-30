// Command api runs the sahiy-agent HTTP service (POST /process, GET /health).
package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/api"
	"github.com/sahiy-backend/sahiy-agent/internal/api/handler"
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

	log := logger.New(cfg.App.LogLevel, cfg.App.LogJSON)
	log.Info("starting sahiy-agent api", "env", cfg.App.Env, "ai_provider", cfg.AI.Provider)

	ctx := context.Background()
	app, err := bootstrap.New(ctx, cfg, log)
	if err != nil {
		return err
	}
	defer app.Close()

	h := handler.New(app.ReplyService, app.Pool, log)
	addr := fmt.Sprintf("%s:%d", cfg.App.Host, cfg.App.Port)
	server := api.NewServer(addr, h, cfg.AI.ServiceToken, log)

	errCh := make(chan error, 1)
	go func() { errCh <- server.Start() }()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)

	select {
	case err := <-errCh:
		return err
	case sig := <-stop:
		log.Info("shutdown signal received", "signal", sig.String())
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		return fmt.Errorf("graceful shutdown: %w", err)
	}
	log.Info("server stopped cleanly")
	return nil
}
