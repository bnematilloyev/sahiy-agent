package sahiy

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/config"
)

// AdminAuth manages admin panel JWT tokens.
type AdminAuth struct {
	cfg    config.Sahiy
	http   *http.Client
	mu     sync.Mutex
	token  string
	expiry time.Time
}

// NewAdminAuth constructs admin authentication.
func NewAdminAuth(cfg config.Sahiy) *AdminAuth {
	return &AdminAuth{
		cfg:  cfg,
		http: &http.Client{Timeout: cfg.Timeout},
	}
}

// Token returns a valid admin bearer token.
func (a *AdminAuth) Token(ctx context.Context) (string, error) {
	if t := strings.TrimSpace(a.cfg.AdminAccessToken); t != "" {
		return t, nil
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.token != "" && time.Now().Before(a.expiry) {
		return a.token, nil
	}
	if a.cfg.AdminUsername == "" || a.cfg.AdminPassword == "" {
		return "", fmt.Errorf("admin: no credentials configured")
	}
	body, _ := json.Marshal(map[string]string{
		"username": a.cfg.AdminUsername,
		"password": a.cfg.AdminPassword,
	})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(a.cfg.BaseURL, "/")+"/api/admin/v1/token", bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := a.http.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		snippet, _ := io.ReadAll(io.LimitReader(resp.Body, 256))
		return "", fmt.Errorf("admin token http %d: %s", resp.StatusCode, snippet)
	}
	var out struct {
		AccessToken string `json:"access_token"`
		Token       string `json:"token"`
		ExpiresIn   int    `json:"expires_in"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", err
	}
	tok := out.AccessToken
	if tok == "" {
		tok = out.Token
	}
	if tok == "" {
		return "", fmt.Errorf("admin: empty token in response")
	}
	ttl := a.cfg.AdminTokenTTL
	if ttl <= 0 {
		ttl = 50 * time.Minute
	}
	a.token = tok
	a.expiry = time.Now().Add(ttl)
	return tok, nil
}

// Invalidate clears the cached token so the next Token call re-authenticates.
// Static SAHIY_ADMIN_ACCESS_TOKEN is left unchanged.
func (a *AdminAuth) Invalidate() {
	if strings.TrimSpace(a.cfg.AdminAccessToken) != "" {
		return
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	a.token = ""
	a.expiry = time.Time{}
}
