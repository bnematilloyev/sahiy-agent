// Package api wires the HTTP router and server.
package api

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"

	"github.com/sahiy-backend/sahiy-agent/internal/api/handler"
	mw "github.com/sahiy-backend/sahiy-agent/internal/api/middleware"
)

// Server wraps the HTTP server and its lifecycle.
type Server struct {
	http *http.Server
	log  *slog.Logger
}

// NewServer builds the router and HTTP server.
//
// serviceToken protects /process and /faq; an empty token disables the guard
// for local development.
func NewServer(addr string, h *handler.Handler, serviceToken string, log *slog.Logger) *Server {
	r := chi.NewRouter()
	r.Use(mw.RequestID)
	// Logging wraps Recover, so a panicking request still produces a normal
	// access-log line (with status 500) instead of vanishing from the log.
	r.Use(mw.Logging(log))
	r.Use(mw.Recover(log))

	if serviceToken == "" {
		// config.Load only permits this in development, but say it out loud so
		// nobody mistakes an open endpoint for a configured one.
		log.Warn("service token is empty: POST /process and POST /faq are UNAUTHENTICATED (development only)")
	}

	// Health is unauthenticated so probes never need the service token.
	r.Get("/health", h.Health)

	r.Group(func(r chi.Router) {
		r.Use(mw.ServiceToken(serviceToken))
		r.Post("/process", h.Process)
		r.Post("/faq", h.IngestFAQ)
	})

	return &Server{
		http: &http.Server{
			Addr:              addr,
			Handler:           r,
			ReadHeaderTimeout: 10 * time.Second,
			ReadTimeout:       30 * time.Second,
			// Answering costs up to two LLM round-trips, so the write budget is
			// generous - but not unbounded, or a stuck handler holds the
			// connection forever.
			WriteTimeout: 120 * time.Second,
			IdleTimeout:  120 * time.Second,
		},
		log: log,
	}
}

// Start begins serving and blocks until the server stops.
func (s *Server) Start() error {
	s.log.Info("http server listening", "addr", s.http.Addr)
	if err := s.http.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		return fmt.Errorf("api: serve: %w", err)
	}
	return nil
}

// Shutdown gracefully stops the server.
func (s *Server) Shutdown(ctx context.Context) error {
	return s.http.Shutdown(ctx)
}
