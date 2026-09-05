package api

import (
	"bytes"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/sahiy-backend/sahiy-agent/internal/api/handler"
)

// The wired server must reject an unauthenticated /process before it ever
// reaches the chat pipeline - a nil ReplyService would panic if it did.
func TestProcessRequiresServiceToken(t *testing.T) {
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := NewServer(":0", handler.New(nil, nil, nil, log), "s3cret", log)

	req := httptest.NewRequest(http.MethodPost, "/process",
		bytes.NewReader([]byte(`{"user_id":"u1","text":"salom"}`)))
	rec := httptest.NewRecorder()
	srv.http.Handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", rec.Code)
	}
}

// Health must stay reachable without the token so probes keep working.
func TestHealthIsUnauthenticated(t *testing.T) {
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := NewServer(":0", handler.New(nil, nil, nil, log), "s3cret", log)

	rec := httptest.NewRecorder()
	srv.http.Handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/health", nil))

	if rec.Code == http.StatusUnauthorized {
		t.Error("health must not require the service token")
	}
}

// Every request carries a request id, generated when the caller omits one, so
// panic logs can be tied back to a specific request.
func TestRequestIDIsAlwaysSet(t *testing.T) {
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := NewServer(":0", handler.New(nil, nil, nil, log), "", log)

	rec := httptest.NewRecorder()
	srv.http.Handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/health", nil))

	if rec.Header().Get("X-Request-ID") == "" {
		t.Error("X-Request-ID header is empty")
	}
}

// A panic anywhere in the authenticated pipeline must surface as a 500, not
// kill the process. Passing a nil ReplyService makes Process panic for real.
func TestPanicInHandlerBecomesInternalError(t *testing.T) {
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := NewServer(":0", handler.New(nil, nil, nil, log), "", log)

	req := httptest.NewRequest(http.MethodPost, "/process",
		bytes.NewReader([]byte(`{"user_id":"u1","text":"salom"}`)))
	rec := httptest.NewRecorder()
	srv.http.Handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Errorf("status = %d, want 500 from the recovered panic", rec.Code)
	}
}

// Timeouts must be set: without them a slow or stuck client holds a connection
// (and a goroutine) indefinitely.
func TestServerHasTimeouts(t *testing.T) {
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := NewServer(":0", handler.New(nil, nil, nil, log), "s3cret", log)

	if srv.http.ReadHeaderTimeout == 0 {
		t.Error("ReadHeaderTimeout is unset")
	}
	if srv.http.ReadTimeout == 0 {
		t.Error("ReadTimeout is unset")
	}
	if srv.http.WriteTimeout == 0 {
		t.Error("WriteTimeout is unset")
	}
	if srv.http.IdleTimeout == 0 {
		t.Error("IdleTimeout is unset")
	}
}

// The ingestion endpoint writes to the knowledge base, so it must sit behind
// the same token as /process rather than being reachable by anyone.
func TestIngestFAQRequiresServiceToken(t *testing.T) {
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := NewServer(":0", handler.New(nil, nil, nil, log), "s3cret", log)

	req := httptest.NewRequest(http.MethodPost, "/faq",
		bytes.NewReader([]byte(`{"question":"q","answer":"a"}`)))
	rec := httptest.NewRecorder()
	srv.http.Handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", rec.Code)
	}
}

// With no FAQ service wired the endpoint must say so rather than panic on a
// nil dependency.
func TestIngestFAQWithoutServiceIsUnavailable(t *testing.T) {
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := NewServer(":0", handler.New(nil, nil, nil, log), "", log)

	req := httptest.NewRequest(http.MethodPost, "/faq",
		bytes.NewReader([]byte(`{"question":"q","answer":"a"}`)))
	rec := httptest.NewRecorder()
	srv.http.Handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("status = %d, want 503", rec.Code)
	}
}
