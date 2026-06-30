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
	"time"
)

// Client is an authenticated HTTP client for the Sahiy Laravel API. It attaches
// a Bearer token to every request and retries once on HTTP 401.
type Client struct {
	baseURL string
	auth    *ServiceUserAuth
	http    *http.Client
	log     *slog.Logger
}

func newClient(baseURL string, auth *ServiceUserAuth, timeout time.Duration, log *slog.Logger) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		auth:    auth,
		http:    &http.Client{Timeout: timeout},
		log:     log,
	}
}

// GetJSON performs an authenticated GET, decodes the JSON response into out.
// On HTTP 401 it invalidates the cached token and retries once.
func (c *Client) GetJSON(ctx context.Context, path string, query url.Values, out any) error {
	return c.GetJSONWithHeaders(ctx, path, query, nil, out)
}

// GetJSONWithHeaders is like GetJSON but allows extra request headers (e.g.
// Accept-Language for product search).
func (c *Client) GetJSONWithHeaders(ctx context.Context, path string, query url.Values, headers map[string]string, out any) error {
	token, err := c.auth.Token(ctx)
	if err != nil {
		return err
	}

	status, err := c.doGetWithHeaders(ctx, path, query, headers, token, out)
	if err != nil {
		return err
	}
	if status != http.StatusUnauthorized {
		return nil
	}

	// Token was revoked server-side: invalidate, re-authenticate, retry once.
	c.log.Info("sahiy: 401 – refreshing token and retrying", "path", path)
	c.auth.Invalidate()
	token, err = c.auth.Token(ctx)
	if err != nil {
		return err
	}
	status, err = c.doGetWithHeaders(ctx, path, query, headers, token, out)
	if err != nil {
		return err
	}
	if status == http.StatusUnauthorized {
		return fmt.Errorf("sahiy: still unauthorized after token refresh")
	}
	return nil
}

func (c *Client) doGetWithHeaders(ctx context.Context, path string, query url.Values, headers map[string]string, token string, out any) (int, error) {
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
	for k, v := range headers {
		req.Header.Set(k, v)
	}

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
		return resp.StatusCode, fmt.Errorf("sahiy http %d: %s", resp.StatusCode, string(snippet))
	}
	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return resp.StatusCode, fmt.Errorf("decode: %w", err)
	}
	return resp.StatusCode, nil
}
