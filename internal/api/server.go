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
// serviceToken protects /process; an empty token disables the guard for local
// development.
func NewServer(addr string, h *handler.Handler, serviceToken string, log *slog.Logger) *Server {
	r := chi.NewRouter()
	r.Use(mw.RequestID)
	r.Use(mw.Logging(log))

	// Health is unauthenticated so probes never need the service token.
	r.Get("/health", h.Health)

	r.Group(func(r chi.Router) {
		r.Use(mw.ServiceToken(serviceToken))
		r.Post("/process", h.Process)
	})

	return &Server{
		http: &http.Server{
			Addr:              addr,
			Handler:           r,
			ReadHeaderTimeout: 10 * time.Second,
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
