// Package middleware holds HTTP middleware for the agent API.
package middleware

import (
	"context"
	"crypto/subtle"
	"log/slog"
	"net/http"
	"runtime/debug"
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

// Recover turns a panic in any handler into a 500 response instead of letting
// it take the whole process down with every other in-flight request.
func Recover(log *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			defer func() {
				rec := recover()
				if rec == nil {
					return
				}
				// A client disconnecting mid-write is not a bug; re-panic so the
				// server handles it the way net/http expects.
				if rec == http.ErrAbortHandler {
					panic(rec)
				}
				log.Error("panic recovered",
					"panic", rec,
					"method", r.Method,
					"path", r.URL.Path,
					"request_id", RequestIDFromContext(r.Context()),
					"stack", string(debug.Stack()),
				)
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusInternalServerError)
				_, _ = w.Write([]byte(`{"message":"internal error"}`))
			}()
			next.ServeHTTP(w, r)
		})
	}
}

// ServiceToken guards routes with a shared secret. An empty token disables the
// guard, which is only allowed in development - config.Load refuses to start a
// non-development process without one, so a missing env var cannot silently
// leave the endpoint open.
func ServiceToken(token string) func(http.Handler) http.Handler {
	expected := []byte(token)
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if len(expected) > 0 && !tokenMatches(expected, r.Header.Get("X-Service-Token")) {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusUnauthorized)
				_, _ = w.Write([]byte(`{"message":"invalid service token"}`))
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// tokenMatches compares in constant time so a wrong token cannot be discovered
// byte by byte from response timing.
func tokenMatches(expected []byte, got string) bool {
	return subtle.ConstantTimeCompare(expected, []byte(got)) == 1
}

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) WriteHeader(code int) {
	w.status = code
	w.ResponseWriter.WriteHeader(code)
}
