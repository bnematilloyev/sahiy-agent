package sahiy

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/url"
	"regexp"
	"strings"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/order"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// phonePattern is a loose heuristic: 7 or more digits, optional +, spaces,
// dashes and parentheses. Used to distinguish a phone from a track number.
var phonePattern = regexp.MustCompile(`^\+?[\d\s\-\(\)]{7,}$`)

// CustomerAPI implements app/order.CustomerLookup and app/identity.CustomerVerifier.
type CustomerAPI struct {
	client         *Client
	daigou         *DaigouAdmin
	daigouList     *DaigouList
	daigouPageSize int
	skuEnabled     bool
	log            *slog.Logger
}

// Lookup resolves a customer query using optional verified identity context.
func (a *CustomerAPI) Lookup(ctx context.Context, req order.LookupRequest) (order.CustomerSnapshot, error) {
	q := strings.TrimSpace(req.Query)
	phone := shared.NormalizePhone(req.VerifiedPhone)
	userID := req.VerifiedUserID

	if track, ok := shared.ExtractTrack(q); ok {
		a.log.Debug("sahiy: track detected in query", "track", track, "verified_user_id", userID)
		if userID > 0 {
			return a.buildSnapshot(ctx, userID, track, phone)
		}
		return a.lookupByTrack(ctx, track)
	}

	if userID > 0 {
		a.log.Debug("sahiy: lookup by verified user id", "user_id", userID)
		return a.buildSnapshot(ctx, userID, "", phone)
	}
	if phone != "" {
		a.log.Debug("sahiy: lookup by verified phone", "phone", phone)
		return a.lookupByPhone(ctx, phone)
	}

	// Strip non-digit chars and check if the result looks like a phone number.
	digitsOnly := strings.Map(func(r rune) rune {
		if r >= '0' && r <= '9' {
			return r
		}
		return -1
	}, q)
	if len(digitsOnly) >= 7 && phonePattern.MatchString(q) {
		a.log.Debug("sahiy: phone detected in query", "phone", q)
		return a.lookupByPhone(ctx, q)
	}

	// Last resort: try each known track-field type in the search API.
	return a.lookupBySearch(ctx, q)
}

// FindUserIDByPhone resolves a Sahiy user id from a phone number.
func (a *CustomerAPI) FindUserIDByPhone(ctx context.Context, phone string) (int64, error) {
	return a.findUserIDByPhone(ctx, phone)
}

// UserExists reports whether a Sahiy user id resolves to a customer record.
func (a *CustomerAPI) UserExists(ctx context.Context, userID int64) (bool, error) {
	if userID < 1 {
		return false, nil
	}
	snap, err := a.buildSnapshot(ctx, userID, "", "")
	if err != nil {
		return false, err
	}
	return snap.UserID() == userID, nil
}

func (a *CustomerAPI) lookupByPhone(ctx context.Context, phone string) (order.CustomerSnapshot, error) {
	userID, err := a.findUserIDByPhone(ctx, phone)
	if err != nil {
		return order.CustomerSnapshot{}, fmt.Errorf("find user by phone: %w", err)
	}
	if userID == 0 {
		return order.NewCustomerSnapshot(0, "", phone, nil), nil
	}
	return a.buildSnapshot(ctx, userID, "", phone)
}

func (a *CustomerAPI) lookupByTrack(ctx context.Context, track string) (order.CustomerSnapshot, error) {
	// Try the dedicated tracking endpoint to find the owner.
	var trackRaw json.RawMessage
	if err := a.client.GetJSON(ctx, "/api/v2/admin/delivery/orders/tracking/"+strings.TrimSpace(track), nil, &trackRaw); err == nil {
		if userID := extractUserIDFromRaw(trackRaw); userID != 0 {
			return a.buildSnapshot(ctx, userID, track, "")
		}
	}
	// Fall back to multi-field search.
	return a.lookupBySearch(ctx, track)
}

func (a *CustomerAPI) lookupBySearch(ctx context.Context, query string) (order.CustomerSnapshot, error) {
	for _, by := range []string{"track_number", "express_num", "tracking", "order_sn", "logistics_sn"} {
		q := url.Values{"search_by": {by}, "query": {query}}
		var raw json.RawMessage
		if err := a.client.GetJSON(ctx, "/api/v2/admin/delivery/orders/search", q, &raw); err != nil {
			a.log.Warn("sahiy: search failed", "search_by", by, "error", err)
			continue
		}
		if userID := extractUserIDFromRaw(raw); userID != 0 {
			a.log.Debug("sahiy: user found via search", "search_by", by, "user_id", userID)
			return a.buildSnapshot(ctx, userID, query, "")
		}
	}
	return order.NewCustomerSnapshot(0, "", "", nil), nil
}

func (a *CustomerAPI) findUserIDByPhone(ctx context.Context, phone string) (int64, error) {
	q := url.Values{"search_by": {"phone"}, "query": {phone}}
	var raw json.RawMessage
	if err := a.client.GetJSON(ctx, "/api/v2/admin/delivery/orders/search", q, &raw); err != nil {
		return 0, err
	}
	return extractUserIDFromRaw(raw), nil
}

// buildSnapshot fetches delivery orders for userID and maps them to the domain model.
// If a specific track was requested, only that order is returned in the snapshot.
func (a *CustomerAPI) buildSnapshot(ctx context.Context, userID int64, requestedTrack, phone string) (order.CustomerSnapshot, error) {
	path := fmt.Sprintf("/api/v2/admin/delivery/orders/user/%d", userID)
	var raw json.RawMessage
	if err := a.client.GetJSON(ctx, path, nil, &raw); err != nil {
		// Return a snapshot with no orders rather than failing; the user exists but
		// their order list is temporarily unavailable.
		a.log.Warn("sahiy: delivery orders unavailable", "user_id", userID, "error", err)
		return order.NewCustomerSnapshot(userID, "", phone, nil), nil
	}

	rows := extractList(raw)
	orders := make([]order.Order, 0, len(rows))
	for _, row := range rows {
		o := mapRowToOrder(row)
		if d := a.daigou; d != nil && a.skuEnabled {
			sn := rawStrFromMap(row, "order_sn", "track_number", "express_num")
			items := d.EnrichOrderItems(ctx, userID, sn, o.Items())
			if len(items) > 0 && (len(o.Items()) == 0 || hasRicherItems(items, o.Items())) {
				o = order.ReconstituteOrder(
					o.TrackNumber(), o.StatusCode(), o.StatusLabel(),
					o.CreatedAt(), o.UpdatedAt(), items,
				)
			}
		}
		orders = append(orders, o)
	}

	// When a specific track was requested, surface only that order.
	if requestedTrack != "" {
		norm := strings.ToUpper(strings.TrimSpace(requestedTrack))
		for _, o := range orders {
			if strings.EqualFold(o.TrackNumber(), norm) || strings.EqualFold(o.TrackNumber(), requestedTrack) {
				return order.NewCustomerSnapshot(userID, "", phone, []order.Order{o}), nil
			}
		}
		// Track may be a daigou order_sn still in China (never in delivery list).
		if dg, ok := a.findDaigouOrder(ctx, userID, requestedTrack); ok {
			return order.NewCustomerSnapshot(userID, "", phone, nil).WithDaigou([]order.Order{dg}, 1), nil
		}
	}

	snapshot := order.NewCustomerSnapshot(userID, "", phone, orders)
	if a.daigouList != nil {
		dgOrders, total := a.fetchDaigou(ctx, userID)
		if len(dgOrders) > 0 {
			snapshot = snapshot.WithDaigou(dgOrders, total)
		}
	}
	return snapshot, nil
}

// fetchDaigou loads the user's China-purchase (daigou) orders and maps them to
// domain Orders tagged with the daigou source.
func (a *CustomerAPI) fetchDaigou(ctx context.Context, userID int64) ([]order.Order, int) {
	size := a.daigouPageSize
	if size <= 0 {
		size = 10
	}
	codes, useFilter := intentStatusCodes("")
	rows, total := a.daigouList.fetchDaigouOrders(ctx, userID, 1, size, codes, useFilter)
	out := make([]order.Order, 0, len(rows))
	for _, row := range rows {
		out = append(out, mapDaigouRow(row))
	}
	return out, total
}

// findDaigouOrder looks up a single daigou order by its order_sn.
func (a *CustomerAPI) findDaigouOrder(ctx context.Context, userID int64, orderSN string) (order.Order, bool) {
	if a.daigouList == nil {
		return order.Order{}, false
	}
	row, ok := a.daigouList.findDaigouBySN(ctx, userID, orderSN, 50, 5)
	if !ok {
		return order.Order{}, false
	}
	return mapDaigouRow(row), true
}

// mapDaigouRow maps a raw daigou JSON row to the domain Order model, using the
// daigou status labels and the order_sn as the identifier.
func mapDaigouRow(row map[string]json.RawMessage) order.Order {
	sn := rawStrFromMap(row, "order_sn", "sn", "client_order_sn")
	statusCode := rawIntFromMap(row, "status")
	statusLabel := daigouLabel(statusCode, "uz")
	createdAt := rawTimeFromMap(row, "created_at")
	updatedAt := rawTimeFromMap(row, "updated_at")

	var items []order.OrderItem
	if rawItems, ok := row["items"]; ok {
		var arr []map[string]json.RawMessage
		if json.Unmarshal(rawItems, &arr) == nil {
			for _, ir := range arr {
				items = append(items, order.NewOrderItem(
					rawStrFromMap(ir, "name", "title", "product_name", "goods_name"),
					rawStrFromMap(ir, "sku", "article", "sku_attr"),
					rawIntFromMap(ir, "quantity", "qty", "count", "num"),
					rawFloatFromMap(ir, "price", "unit_price"),
					rawStrFromMap(ir, "currency"),
					rawStrFromMap(ir, "image", "photo", "image_url", "goods_image"),
				))
			}
		}
	}
	return order.ReconstituteSourcedOrder(order.SourceDaigou, sn, statusCode, statusLabel, createdAt, updatedAt, items)
}

// mapRowToOrder maps a raw JSON delivery-order row to the domain model. It is
// intentionally lenient: missing or wrongly-typed fields become zero values.
func mapRowToOrder(row map[string]json.RawMessage) order.Order {
	track := rawStrFromMap(row, "track_number", "express_num", "tracking_number", "order_sn")
	statusCode := rawIntFromMap(row, "status")
	statusLabel := deliveryLabel(statusCode, "uz")
	createdAt := rawTimeFromMap(row, "created_at")
	updatedAt := rawTimeFromMap(row, "updated_at")

	var items []order.OrderItem
	if rawItems, ok := row["items"]; ok {
		var arr []map[string]json.RawMessage
		if json.Unmarshal(rawItems, &arr) == nil {
			for _, ir := range arr {
				items = append(items, order.NewOrderItem(
					rawStrFromMap(ir, "name", "title", "product_name"),
					rawStrFromMap(ir, "sku", "article"),
					rawIntFromMap(ir, "quantity", "qty", "count"),
					rawFloatFromMap(ir, "price", "unit_price"),
					rawStrFromMap(ir, "currency"),
					rawStrFromMap(ir, "image", "photo", "image_url"),
				))
			}
		}
	}
	return order.ReconstituteOrder(track, statusCode, statusLabel, createdAt, updatedAt, items)
}

func hasRicherItems(enriched, existing []order.OrderItem) bool {
	if len(enriched) == 0 {
		return false
	}
	if len(enriched) != len(existing) {
		return true
	}
	for i := range enriched {
		if enriched[i].ImageURL() != "" && existing[i].ImageURL() == "" {
			return true
		}
		if enriched[i].Name() != "" && existing[i].Name() == "" {
			return true
		}
	}
	return false
}

// extractList tries common JSON envelope shapes to find a list of order objects:
// top-level array, or an object with "data", "orders", "items", or "results" keys.
func extractList(raw json.RawMessage) []map[string]json.RawMessage {
	if raw == nil {
		return nil
	}
	var arr []map[string]json.RawMessage
	if json.Unmarshal(raw, &arr) == nil {
		return arr
	}
	var obj map[string]json.RawMessage
	if json.Unmarshal(raw, &obj) != nil {
		return nil
	}
	for _, key := range []string{"data", "orders", "items", "results"} {
		v, ok := obj[key]
		if !ok {
			continue
		}
		var inner []map[string]json.RawMessage
		if json.Unmarshal(v, &inner) == nil {
			return inner
		}
		// Recurse into a nested object with the same envelope keys.
		if nested := extractList(v); len(nested) > 0 {
			return nested
		}
	}
	return nil
}

// extractUserIDFromRaw searches a JSON blob for the first recognizable user_id,
// tolerating various nesting depths up to ~4 levels.
func extractUserIDFromRaw(raw json.RawMessage) int64 {
	if raw == nil {
		return 0
	}
	// Try list of rows first.
	for _, row := range extractList(raw) {
		if id := rawInt64FromMap(row, "user_id", "userId", "customer_id", "customerId"); id != 0 {
			return id
		}
	}
	// Try top-level object.
	var obj map[string]json.RawMessage
	if json.Unmarshal(raw, &obj) != nil {
		return 0
	}
	if id := rawInt64FromMap(obj, "user_id", "userId", "customer_id", "customerId"); id != 0 {
		return id
	}
	for _, k := range []string{"user", "customer", "order", "delivery_order", "data", "result"} {
		if v, ok := obj[k]; ok {
			if id := extractUserIDFromRaw(v); id != 0 {
				return id
			}
		}
	}
	return 0
}

// --- low-level JSON helpers ------------------------------------------------

func rawStrFromMap(m map[string]json.RawMessage, keys ...string) string {
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

func rawIntFromMap(m map[string]json.RawMessage, keys ...string) int {
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

func rawInt64FromMap(m map[string]json.RawMessage, keys ...string) int64 {
	for _, k := range keys {
		if v, ok := m[k]; ok {
			var n int64
			if json.Unmarshal(v, &n) == nil && n != 0 {
				return n
			}
		}
	}
	return 0
}

func rawFloatFromMap(m map[string]json.RawMessage, keys ...string) float64 {
	for _, k := range keys {
		if v, ok := m[k]; ok {
			var f float64
			if json.Unmarshal(v, &f) == nil {
				return f
			}
		}
	}
	return 0
}

var timeLayouts = []string{
	time.RFC3339,
	"2006-01-02T15:04:05",
	"2006-01-02 15:04:05",
	"2006-01-02",
}

func rawTimeFromMap(m map[string]json.RawMessage, keys ...string) time.Time {
	for _, k := range keys {
		if v, ok := m[k]; ok {
			var s string
			if json.Unmarshal(v, &s) == nil && s != "" {
				for _, layout := range timeLayouts {
					if t, err := time.Parse(layout, s); err == nil {
						return t
					}
				}
			}
		}
	}
	return time.Time{}
}
