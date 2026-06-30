package handler

import (
	"context"
	"net/http"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/api/schema"
)

// Health reports service liveness and database connectivity.
func (h *Handler) Health(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	dbStatus := "ok"
	status := http.StatusOK
	if err := h.pool.Ping(ctx); err != nil {
		dbStatus = "down"
		status = http.StatusServiceUnavailable
		h.log.Error("health: db ping failed", "error", err)
	}

	writeJSON(w, status, schema.HealthResponse{
		Status:  map[bool]string{true: "ok", false: "degraded"}[status == http.StatusOK],
		Service: "sahiy-agent",
		DB:      dbStatus,
	})
}
