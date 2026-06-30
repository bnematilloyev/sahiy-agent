// Package handler implements the agent's HTTP endpoints (interface adapters).
package handler

import (
	"encoding/json"
	"log/slog"
	"net/http"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sahiy-backend/sahiy-agent/internal/api/schema"
	"github.com/sahiy-backend/sahiy-agent/internal/app/chat"
)

// Handler holds the dependencies shared by the HTTP endpoints.
type Handler struct {
	reply *chat.ReplyService
	pool  *pgxpool.Pool
	log   *slog.Logger
}

// New constructs an HTTP handler set.
func New(reply *chat.ReplyService, pool *pgxpool.Pool, log *slog.Logger) *Handler {
	return &Handler{reply: reply, pool: pool, log: log}
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, schema.ErrorResponse{Message: msg})
}
