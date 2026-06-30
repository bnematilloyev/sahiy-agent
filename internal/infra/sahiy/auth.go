// Package sahiy provides infrastructure adapters for the Sahiy Laravel API:
// token caching, an authenticated HTTP client, and the customer order lookup.
package sahiy

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/config"
)

const (
	loginPath   = "/api/v2/service/user/login/"
	refreshPath = "/api/v2/service/user/refresh-token/"
)

type cachedToken struct {
	accessToken  string
	refreshToken string
	expiresAt    time.Time
}

// ServiceUserAuth caches a bearer token and re-authenticates before the token
// expires (respecting a configurable buffer). Safe for concurrent use.
type ServiceUserAuth struct {
	baseURL  string
	phone    string
	password string
	deviceID string
	buffer   time.Duration
	http     *http.Client
	log      *slog.Logger

	mu    sync.Mutex
	cache *cachedToken
}

func newServiceUserAuth(cfg config.Sahiy, httpClient *http.Client, log *slog.Logger) *ServiceUserAuth {
	return &ServiceUserAuth{
		baseURL:  strings.TrimRight(cfg.BaseURL, "/"),
		phone:    strings.TrimSpace(cfg.ServiceUserPhone),
		password: cfg.ServiceUserPass,
		deviceID: cfg.ServiceUserDevice,
		buffer:   cfg.TokenBuffer,
		http:     httpClient,
		log:      log,
	}
}

// Token returns a valid bearer token, refreshing or re-logging in as needed.
func (a *ServiceUserAuth) Token(ctx context.Context) (string, error) {
	a.mu.Lock()
	defer a.mu.Unlock()

	if a.cache != nil && !a.isExpired(a.cache) {
		return a.cache.accessToken, nil
	}

	// Attempt a lightweight refresh before falling back to a full login.
	if a.cache != nil && a.cache.refreshToken != "" {
		tok, err := a.doRefresh(ctx, a.cache.refreshToken)
		if err == nil {
			a.cache = tok
			return tok.accessToken, nil
		}
		a.log.Warn("sahiy: token refresh failed, falling back to login", "error", err)
	}

	tok, err := a.doLogin(ctx)
	if err != nil {
		return "", fmt.Errorf("sahiy: login: %w", err)
	}
	a.cache = tok
	return tok.accessToken, nil
}

// Invalidate forces the next Token call to re-authenticate. Called by the
// client on HTTP 401 to recover from a server-side token revocation.
func (a *ServiceUserAuth) Invalidate() {
	a.mu.Lock()
	a.cache = nil
	a.mu.Unlock()
}

func (a *ServiceUserAuth) isExpired(c *cachedToken) bool {
	return time.Now().After(c.expiresAt.Add(-a.buffer))
}

func (a *ServiceUserAuth) doLogin(ctx context.Context) (*cachedToken, error) {
	return a.postToken(ctx, a.baseURL+loginPath, map[string]string{
		"phone":     a.phone,
		"password":  a.password,
		"device_id": a.deviceID,
	})
}

func (a *ServiceUserAuth) doRefresh(ctx context.Context, refreshToken string) (*cachedToken, error) {
	return a.postToken(ctx, a.baseURL+refreshPath, map[string]string{
		"refresh_token": refreshToken,
	})
}

func (a *ServiceUserAuth) postToken(ctx context.Context, url string, payload any) (*cachedToken, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := a.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("do: %w", err)
	}
	defer resp.Body.Close()

	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("http %d: %s", resp.StatusCode, string(raw))
	}
	return parseTokenResponse(raw)
}

// parseTokenResponse is intentionally lenient: it handles both flat and
// {data:{...}} envelopes and accepts either "access_token" or "token" keys.
func parseTokenResponse(raw []byte) (*cachedToken, error) {
	var envelope map[string]json.RawMessage
	if err := json.Unmarshal(raw, &envelope); err != nil {
		return nil, fmt.Errorf("unmarshal: %w", err)
	}

	// Flatten a nested "data" key into the top level without overwriting.
	if d, ok := envelope["data"]; ok {
		var nested map[string]json.RawMessage
		if json.Unmarshal(d, &nested) == nil {
			for k, v := range nested {
				if _, exists := envelope[k]; !exists {
					envelope[k] = v
				}
			}
		}
	}

	access := rawStr(envelope, "access_token", "token")
	if access == "" {
		return nil, fmt.Errorf("no access_token in token response")
	}
	refresh := rawStr(envelope, "refresh_token")
	ttl := 3600
	if n := rawInt(envelope, "expires_in", "expiresIn"); n > 0 {
		ttl = n
	}
	return &cachedToken{
		accessToken:  access,
		refreshToken: refresh,
		expiresAt:    time.Now().Add(time.Duration(ttl) * time.Second),
	}, nil
}

// rawStr returns the first non-empty string value for any of the given keys.
func rawStr(m map[string]json.RawMessage, keys ...string) string {
	for _, k := range keys {
		if v, ok := m[k]; ok {
			var s string
			if json.Unmarshal(v, &s) == nil && s != "" {
				return s
			}
		}
	}
	return ""
}

// rawInt returns the first non-zero integer value for any of the given keys.
func rawInt(m map[string]json.RawMessage, keys ...string) int {
	for _, k := range keys {
		if v, ok := m[k]; ok {
			var n int
			if json.Unmarshal(v, &n) == nil {
				return n
			}
		}
	}
	return 0
}
