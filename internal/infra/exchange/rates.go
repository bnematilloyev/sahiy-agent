// Package exchange provides CNY→UZS rate fetching with in-memory cache.
package exchange

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/config"
)

// Provider returns the CNY→UZS exchange rate.
type Provider struct {
	apiURL   string
	uuid     string
	fallback float64
	ttl      time.Duration
	http     *http.Client

	mu    sync.RWMutex
	rate  float64
	cache time.Time
}

// NewProvider constructs a rate provider.
func NewProvider(cfg config.Exchange, timeout time.Duration) *Provider {
	return &Provider{
		apiURL:   cfg.APIURL,
		uuid:     cfg.ClientUUID,
		fallback: cfg.UZSFallback,
		ttl:      cfg.CacheTTL,
		http:     &http.Client{Timeout: timeout},
	}
}

// CNYToUZS returns the cached or freshly fetched rate.
func (p *Provider) CNYToUZS(ctx context.Context) float64 {
	p.mu.RLock()
	if p.rate > 0 && time.Since(p.cache) < p.ttl {
		r := p.rate
		p.mu.RUnlock()
		return r
	}
	p.mu.RUnlock()

	rate, err := p.fetch(ctx)
	if err != nil || rate <= 0 {
		return p.fallback
	}
	p.mu.Lock()
	p.rate = rate
	p.cache = time.Now()
	p.mu.Unlock()
	return rate
}

func (p *Provider) fetch(ctx context.Context) (float64, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, p.apiURL, nil)
	if err != nil {
		return 0, err
	}
	if p.uuid != "" {
		req.Header.Set("x-uuid", p.uuid)
	}
	resp, err := p.http.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return 0, err
	}
	return parseCNYUZS(body)
}

func parseCNYUZS(body []byte) (float64, error) {
	var root map[string]json.RawMessage
	if err := json.Unmarshal(body, &root); err != nil {
		return 0, err
	}
	raw, ok := root["data"]
	if !ok {
		return 0, fmt.Errorf("exchange: no data field")
	}
	var rows []map[string]any
	if err := json.Unmarshal(raw, &rows); err != nil {
		return 0, err
	}
	for _, row := range rows {
		from, _ := row["from"].(string)
		code, _ := row["currency_code"].(string)
		if from != "CNY" && from != "cny" {
			continue
		}
		if code != "UZS" && code != "uzs" {
			continue
		}
		switch v := row["rate"].(type) {
		case float64:
			if v > 0 {
				return v, nil
			}
		}
	}
	return 0, fmt.Errorf("exchange: CNY/UZS not found")
}
