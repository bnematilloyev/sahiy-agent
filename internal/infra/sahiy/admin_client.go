package sahiy

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/config"
)

// AdminClient performs authenticated GET requests against admin endpoints.
type AdminClient struct {
	baseURL string
	auth    *AdminAuth
	http    *http.Client
	log     *slog.Logger
}

// NewAdminClient constructs an admin HTTP client.
func NewAdminClient(cfg config.Sahiy, auth *AdminAuth, log *slog.Logger) *AdminClient {
	return &AdminClient{
		baseURL: strings.TrimRight(cfg.BaseURL, "/"),
		auth:    auth,
		http:    &http.Client{Timeout: cfg.Timeout},
		log:     log,
	}
}

// GetJSON performs an authenticated admin GET and decodes JSON into out.
// Returns (false, nil) when no admin token is configured.
func (c *AdminClient) GetJSON(ctx context.Context, path string, query url.Values, out any) (ok bool, err error) {
	token, err := c.auth.Token(ctx)
	if err != nil {
		return false, err
	}
	if token == "" {
		return false, nil
	}

	status, err := c.doGet(ctx, path, query, token, out)
	if err != nil {
		return false, err
	}
	if status != http.StatusUnauthorized {
		return true, nil
	}

	c.log.Info("sahiy admin: 401 – refreshing token and retrying", "path", path)
	c.auth.Invalidate()
	token, err = c.auth.Token(ctx)
	if err != nil {
		return false, err
	}
	if token == "" {
		return false, nil
	}
	status, err = c.doGet(ctx, path, query, token, out)
	if err != nil {
		return false, err
	}
	if status == http.StatusUnauthorized {
		return false, fmt.Errorf("sahiy admin: still unauthorized after token refresh")
	}
	return true, nil
}

func (c *AdminClient) doGet(ctx context.Context, path string, query url.Values, token string, out any) (int, error) {
	u := c.baseURL + path
	if len(query) > 0 {
		u += "?" + query.Encode()
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return 0, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Accept", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return 0, fmt.Errorf("do: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusUnauthorized {
		return http.StatusUnauthorized, nil
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		snippet, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return resp.StatusCode, fmt.Errorf("sahiy admin http %d: %s", resp.StatusCode, string(snippet))
	}
	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return resp.StatusCode, fmt.Errorf("decode: %w", err)
	}
	return resp.StatusCode, nil
}

// extractSingleOrder finds one order object in common admin response envelopes.
func extractSingleOrder(raw json.RawMessage) map[string]json.RawMessage {
	if raw == nil {
		return nil
	}
	items := extractList(raw)
	if len(items) > 0 {
		return items[0]
	}
	var obj map[string]json.RawMessage
	if json.Unmarshal(raw, &obj) != nil {
		return nil
	}
	if _, ok := obj["id"]; ok {
		return obj
	}
	if _, ok := obj["order_sn"]; ok {
		return obj
	}
	if data, ok := obj["data"]; ok {
		return extractSingleOrder(data)
	}
	return nil
}
