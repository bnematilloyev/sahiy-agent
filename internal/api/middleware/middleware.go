// Package middleware holds HTTP middleware for the agent API.
package middleware

import (
	"context"
	"log/slog"
	"net/http"
	"time"

	"github.com/google/uuid"
)

type ctxKey string

const ctxKeyRequestID ctxKey = "request_id"

// RequestID ensures every request has an X-Request-ID, generating one when the
// caller did not supply it, and stores it in the context for downstream logging.
func RequestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rid := r.Header.Get("X-Request-ID")
		if rid == "" {
			rid = uuid.NewString()
		}
		w.Header().Set("X-Request-ID", rid)
		ctx := context.WithValue(r.Context(), ctxKeyRequestID, rid)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// RequestIDFromContext returns the request id stored by the RequestID middleware.
func RequestIDFromContext(ctx context.Context) string {
	v, _ := ctx.Value(ctxKeyRequestID).(string)
	return v
}

// Logging logs method, path, status and duration for each request.
func Logging(log *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			sw := &statusWriter{ResponseWriter: w, status: http.StatusOK}
			next.ServeHTTP(sw, r)
			log.Info("http request",
				"method", r.Method,
				"path", r.URL.Path,
				"status", sw.status,
				"duration_ms", time.Since(start).Milliseconds(),
				"request_id", RequestIDFromContext(r.Context()),
			)
		})
	}
}

// ServiceToken guards routes with a shared secret. When token is empty the guard
// is disabled (useful in local development).
func ServiceToken(token string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if token != "" && r.Header.Get("X-Service-Token") != token {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusUnauthorized)
				_, _ = w.Write([]byte(`{"message":"invalid service token"}`))
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) WriteHeader(code int) {
	w.status = code
	w.ResponseWriter.WriteHeader(code)
}
