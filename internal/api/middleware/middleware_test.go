package middleware

import (
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
)

func discardLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

func serve(h http.Handler, req *http.Request) *httptest.ResponseRecorder {
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

// A panic in a handler must become a 500 for that one request, never take the
// process down with every other in-flight request.
func TestRecoverTurnsPanicIntoInternalError(t *testing.T) {
	handler := Recover(discardLogger())(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		panic("boom")
	}))

	rec := serve(handler, httptest.NewRequest(http.MethodPost, "/process", nil))

	if rec.Code != http.StatusInternalServerError {
		t.Errorf("status = %d, want 500", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
		t.Errorf("Content-Type = %q, want application/json", ct)
	}
}

// http.ErrAbortHandler is net/http's own signal for a client that went away.
// Swallowing it would break the server's connection handling.
func TestRecoverRepanicsAbortHandler(t *testing.T) {
	defer func() {
		if rec := recover(); rec != http.ErrAbortHandler {
			t.Errorf("recovered %v, want ErrAbortHandler to propagate", rec)
		}
	}()

	handler := Recover(discardLogger())(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		panic(http.ErrAbortHandler)
	}))
	serve(handler, httptest.NewRequest(http.MethodPost, "/process", nil))
}

func TestRecoverPassesNormalRequestsThrough(t *testing.T) {
	handler := Recover(discardLogger())(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("fine"))
	}))

	rec := serve(handler, httptest.NewRequest(http.MethodGet, "/health", nil))

	if rec.Code != http.StatusOK || rec.Body.String() != "fine" {
		t.Errorf("status = %d body = %q, want 200 / fine", rec.Code, rec.Body.String())
	}
}

func okHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
}

func TestServiceTokenRejectsWrongAndMissingToken(t *testing.T) {
	handler := ServiceToken("s3cret")(okHandler())

	for name, token := range map[string]string{
		"missing": "",
		"wrong":   "nope",
		"prefix":  "s3cre",
		"longer":  "s3cretx",
	} {
		req := httptest.NewRequest(http.MethodPost, "/process", nil)
		if token != "" {
			req.Header.Set("X-Service-Token", token)
		}
		if rec := serve(handler, req); rec.Code != http.StatusUnauthorized {
			t.Errorf("%s token: status = %d, want 401", name, rec.Code)
		}
	}
}

func TestServiceTokenAcceptsCorrectToken(t *testing.T) {
	handler := ServiceToken("s3cret")(okHandler())

	req := httptest.NewRequest(http.MethodPost, "/process", nil)
	req.Header.Set("X-Service-Token", "s3cret")

	if rec := serve(handler, req); rec.Code != http.StatusOK {
		t.Errorf("status = %d, want 200", rec.Code)
	}
}

// An empty token disables the guard. config.Load only allows that in
// development; this test pins the documented behaviour so it cannot drift.
func TestServiceTokenEmptyDisablesGuard(t *testing.T) {
	handler := ServiceToken("")(okHandler())

	if rec := serve(handler, httptest.NewRequest(http.MethodPost, "/process", nil)); rec.Code != http.StatusOK {
		t.Errorf("status = %d, want 200 when the guard is disabled", rec.Code)
	}
}
