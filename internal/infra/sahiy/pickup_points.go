package sahiy

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"sync"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/pickup"
)

const pickupPointsPath = "/api/admin/pickup-points/"

// PickupPointsAPI fetches pickup points with pagination and cache.
type PickupPointsAPI struct {
	client *Client
	ttl    time.Duration

	mu      sync.RWMutex
	cached  []pickup.Point
	cacheAt time.Time
}

// NewPickupPointsAPI constructs the pickup points client.
func NewPickupPointsAPI(client *Client, ttl time.Duration) *PickupPointsAPI {
	return &PickupPointsAPI{client: client, ttl: ttl}
}

// All returns all pickup points, using cache when fresh.
func (a *PickupPointsAPI) All(ctx context.Context) ([]pickup.Point, error) {
	a.mu.RLock()
	if len(a.cached) > 0 && time.Since(a.cacheAt) < a.ttl {
		out := a.cached
		a.mu.RUnlock()
		return out, nil
	}
	a.mu.RUnlock()

	points, err := a.fetchAll(ctx)
	if err != nil {
		return nil, err
	}
	a.mu.Lock()
	a.cached = points
	a.cacheAt = time.Now()
	a.mu.Unlock()
	return points, nil
}

func (a *PickupPointsAPI) fetchAll(ctx context.Context) ([]pickup.Point, error) {
	const perPage = 50
	var all []pickup.Point
	for page := 1; page <= 20; page++ {
		q := url.Values{"page": {fmt.Sprintf("%d", page)}, "per_page": {fmt.Sprintf("%d", perPage)}}
		var raw json.RawMessage
		if err := a.client.GetJSON(ctx, pickupPointsPath, q, &raw); err != nil {
			if page == 1 {
				return nil, err
			}
			break
		}
		rows := extractList(raw)
		if len(rows) == 0 {
			break
		}
		for _, row := range rows {
			all = append(all, normalizePickup(row))
		}
		if len(rows) < perPage {
			break
		}
	}
	return all, nil
}

func normalizePickup(row map[string]json.RawMessage) pickup.Point {
	id := int64(rawIntFromMap(row, "id"))
	name := localizedText(row, "name")
	address := localizedText(row, "address")
	phone := rawStrFromMap(row, "phone")
	ptype := rawIntFromMap(row, "type")
	typeLabel := rawStrFromMap(row, "type_name")
	if typeLabel == "" {
		if ptype == 1 {
			typeLabel = "Filial"
		} else {
			typeLabel = "Postomat"
		}
	}
	return pickup.NewPoint(id, int64(rawIntFromMap(row, "region_id", "regionId")), name, address, phone, typeLabel, ptype,
		rawStrFromMap(row, "region_name"), rawStrFromMap(row, "city_name"))
}

func localizedText(row map[string]json.RawMessage, key string) string {
	v, ok := row[key]
	if !ok {
		return ""
	}
	var s string
	if json.Unmarshal(v, &s) == nil && s != "" {
		return s
	}
	var obj map[string]string
	if json.Unmarshal(v, &obj) == nil {
		for _, k := range []string{"uz", "ru", "en"} {
			if t := obj[k]; t != "" {
				return t
			}
		}
	}
	return ""
}
