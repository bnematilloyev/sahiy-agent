package sahiy

import (
	"context"
	"encoding/json"
	"sync"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/catalog"
)

const categoriesPath = "/api/client/1688-categories"

// CategoriesAPI fetches the 1688 category tree with in-memory cache.
type CategoriesAPI struct {
	client *Client
	ttl    time.Duration

	mu      sync.RWMutex
	cached  []catalog.Category
	cacheAt time.Time
}

// NewCategoriesAPI constructs the categories client.
func NewCategoriesAPI(client *Client, ttl time.Duration) *CategoriesAPI {
	return &CategoriesAPI{client: client, ttl: ttl}
}

// All returns cached categories (for lookups).
func (a *CategoriesAPI) All(ctx context.Context) ([]catalog.Category, error) {
	return a.fetchAll(ctx)
}

// FindByID returns one category by id.
func (a *CategoriesAPI) FindByID(ctx context.Context, id int64) (catalog.Category, bool, error) {
	all, err := a.fetchAll(ctx)
	if err != nil {
		return catalog.Category{}, false, err
	}
	for _, c := range all {
		if c.ID() == id {
			return c, true, nil
		}
	}
	return catalog.Category{}, false, nil
}

// Children returns direct child categories.
func (a *CategoriesAPI) Children(ctx context.Context, parentID int64) ([]catalog.Category, error) {
	all, err := a.fetchAll(ctx)
	if err != nil {
		return nil, err
	}
	var out []catalog.Category
	for _, c := range all {
		if c.ParentID() == parentID {
			out = append(out, c)
		}
	}
	return out, nil
}

// RootCategories returns top-level categories (parent_id == 0).
func (a *CategoriesAPI) RootCategories(ctx context.Context) ([]catalog.Category, error) {
	all, err := a.fetchAll(ctx)
	if err != nil {
		return nil, err
	}
	var roots []catalog.Category
	for _, c := range all {
		if c.ParentID() == 0 {
			roots = append(roots, c)
		}
	}
	return roots, nil
}

func (a *CategoriesAPI) fetchAll(ctx context.Context) ([]catalog.Category, error) {
	a.mu.RLock()
	if len(a.cached) > 0 && time.Since(a.cacheAt) < a.ttl {
		out := a.cached
		a.mu.RUnlock()
		return out, nil
	}
	a.mu.RUnlock()

	var raw json.RawMessage
	if err := a.client.GetJSON(ctx, categoriesPath, nil, &raw); err != nil {
		return nil, err
	}
	cats := mapCategories(raw)
	a.mu.Lock()
	a.cached = cats
	a.cacheAt = time.Now()
	a.mu.Unlock()
	return cats, nil
}

func mapCategories(raw json.RawMessage) []catalog.Category {
	rows := extractList(raw)
	out := make([]catalog.Category, 0, len(rows))
	for _, row := range rows {
		id := int64(rawIntFromMap(row, "id"))
		parent := int64(rawIntFromMap(row, "parent_id", "parentId", "pid"))
		name := rawStrFromMap(row, "name", "title", "category_name")
		if name == "" {
			continue
		}
		out = append(out, catalog.NewCategory(id, parent, name))
	}
	return out
}
