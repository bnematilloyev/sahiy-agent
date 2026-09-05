package llm

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
)

func TestAnthropicClient_Complete_ParsesUsage(t *testing.T) {
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"content": [{"type": "text", "text": "hello"}],
			"usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 3, "cache_creation_input_tokens": 1}
		}`))
	}))
	defer srv.Close()

	c := newTestAnthropicClient(t, srv.URL)
	out, err := c.Complete(t.Context(), ai.CompletionRequest{
		System: "sys", Messages: []ai.Message{{Role: ai.RoleUser, Content: "hi"}}, Temperature: 0.2,
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if out.Text != "hello" {
		t.Fatalf("Text = %q", out.Text)
	}
	if out.Usage.InputTokens != 10 || out.Usage.OutputTokens != 5 ||
		out.Usage.CacheReadInputTokens != 3 || out.Usage.CacheCreationInputTokens != 1 {
		t.Fatalf("Usage = %+v", out.Usage)
	}
	if gotBody["temperature"] != 0.2 {
		t.Fatalf("expected temperature 0.2 in request, got %v", gotBody["temperature"])
	}
}

func TestAnthropicClient_Complete_CachesSystemPrompt(t *testing.T) {
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"content": [{"type": "text", "text": "hi"}],
			"usage": {"input_tokens": 5000, "output_tokens": 5, "cache_read_input_tokens": 4900}
		}`))
	}))
	defer srv.Close()

	c := newTestAnthropicClient(t, srv.URL)
	out, err := c.Complete(t.Context(), ai.CompletionRequest{
		System: "You are a helpful assistant.", Messages: []ai.Message{{Role: ai.RoleUser, Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if out.Usage.CacheReadInputTokens != 4900 {
		t.Fatalf("CacheReadInputTokens = %d", out.Usage.CacheReadInputTokens)
	}

	system, ok := gotBody["system"].([]any)
	if !ok || len(system) != 1 {
		t.Fatalf("expected system to be a single-block array, got %v", gotBody["system"])
	}
	block, ok := system[0].(map[string]any)
	if !ok {
		t.Fatalf("system block is not an object: %v", system[0])
	}
	cc, ok := block["cache_control"].(map[string]any)
	if !ok || cc["type"] != "ephemeral" {
		t.Fatalf("expected system block to carry ephemeral cache_control, got %v", block["cache_control"])
	}
	if block["text"] != "You are a helpful assistant." {
		t.Fatalf("system text = %v", block["text"])
	}
}

func TestAnthropicClient_Complete_NoSystemOmitsField(t *testing.T) {
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"content": [{"type": "text", "text": "hi"}], "usage": {}}`))
	}))
	defer srv.Close()

	c := newTestAnthropicClient(t, srv.URL)
	if _, err := c.Complete(t.Context(), ai.CompletionRequest{Messages: []ai.Message{{Role: ai.RoleUser, Content: "hi"}}}); err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if _, present := gotBody["system"]; present {
		t.Fatalf("expected no system field when System is empty, got %v", gotBody["system"])
	}
}

func TestAnthropicClient_Complete_RetriesWithoutTemperature(t *testing.T) {
	var calls int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		calls++
		if _, hasTemp := body["temperature"]; hasTemp {
			w.WriteHeader(http.StatusBadRequest)
			_, _ = w.Write([]byte(`{"error":{"type":"invalid_request_error","message":"temperature: Extra inputs are not permitted"}}`))
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 1, "output_tokens": 1}}`))
	}))
	defer srv.Close()

	c := newTestAnthropicClient(t, srv.URL)
	req := ai.CompletionRequest{Messages: []ai.Message{{Role: ai.RoleUser, Content: "hi"}}, Temperature: 0.3}

	out, err := c.Complete(t.Context(), req)
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if out.Text != "ok" {
		t.Fatalf("Text = %q", out.Text)
	}
	if calls != 2 {
		t.Fatalf("expected 1 failed + 1 retry call, got %d calls", calls)
	}

	// The client should remember not to send temperature again.
	calls = 0
	if _, err := c.Complete(t.Context(), req); err != nil {
		t.Fatalf("second Complete: %v", err)
	}
	if calls != 1 {
		t.Fatalf("expected a single call once temperature is known unsupported, got %d", calls)
	}
}

func newTestAnthropicClient(t *testing.T, url string) *AnthropicClient {
	t.Helper()
	original := anthropicURL
	anthropicURL = url
	t.Cleanup(func() { anthropicURL = original })
	return NewAnthropicClient("test-key", "claude-test", 5*time.Second)
}
