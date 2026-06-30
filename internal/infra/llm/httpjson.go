// Package llm provides Completer adapters (Anthropic, OpenAI, a rules-based
// fallback) and a failover chain that ties them together.
package llm

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

// postJSON sends body as JSON to url with the given headers and decodes the JSON
// response into out. Non-2xx responses become errors carrying the status and a
// snippet of the body.
func postJSON(ctx context.Context, client *http.Client, url string, headers map[string]string, body, out any) error {
	payload, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(payload))
	if err != nil {
		return fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("do request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		snippet, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return &httpError{status: resp.StatusCode, body: string(snippet)}
	}

	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	return nil
}

// httpError captures a non-2xx provider response.
type httpError struct {
	status int
	body   string
}

func (e *httpError) Error() string {
	return fmt.Sprintf("provider http %d: %s", e.status, e.body)
}
