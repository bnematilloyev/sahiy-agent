package sahiy

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
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
	// skuEnrichMaxOrders caps how many orders one lookup enriches; <= 0 is
	// uncapped. skuEnrichConcurrency bounds how many run at once.
	skuEnrichMaxOrders   int
	skuEnrichConcurrency int
	log                  *slog.Logger
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
		return a.buildSnapshotWithIntent(ctx, userID, "", phone, order.ParseListIntent(q))
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

// buildSnapshot fetches every source for userID. Used by the paths that look up
// a specific parcel, where narrowing by a list intent would be wrong: the
// customer named one order, so it must be found wherever it lives.
func (a *CustomerAPI) buildSnapshot(ctx context.Context, userID int64, requestedTrack, phone string) (order.CustomerSnapshot, error) {
	return a.buildSnapshotWithIntent(ctx, userID, requestedTrack, phone, order.DefaultListIntent())
}

// buildSnapshotWithIntent fetches only the sources the question asks for and
// keeps only the rows matching its filter. Skipping unwanted sources is the
// point: it removes whole HTTP round-trips from the answer path, which no
// amount of post-filtering could.
func (a *CustomerAPI) buildSnapshotWithIntent(
	ctx context.Context,
	userID int64,
	requestedTrack, phone string,
	intent order.ListIntent,
) (order.CustomerSnapshot, error) {
	var mapped []deliveryRow
	if intent.WantsSource(order.SourceDelivery) {
		path := fmt.Sprintf("/api/v2/admin/delivery/orders/user/%d", userID)
		var raw json.RawMessage
		if err := a.client.GetJSON(ctx, path, nil, &raw); err != nil {
			// Return a snapshot with no orders rather than failing; the user exists but
			// their order list is temporarily unavailable.
			a.log.Warn("sahiy: delivery orders unavailable", "user_id", userID, "error", err)
			return order.NewCustomerSnapshot(userID, "", phone, nil), nil
		}

		// Rows are mapped first and enriched afterwards. Enriching inside this
		// loop would spend one or two admin-API calls on every order the
		// customer has ever placed, including the ones about to be discarded.
		rows := extractList(raw)
		mapped = make([]deliveryRow, 0, len(rows))
		for _, row := range rows {
			mapped = append(mapped, deliveryRow{
				order: mapRowToOrder(row),
				sn:    rawStrFromMap(row, "order_sn", "track_number", "express_num"),
			})
		}
	}

	// When a specific track was requested, surface only that order - and pay
	// for enriching that one alone.
	if requestedTrack != "" {
		norm := strings.ToUpper(strings.TrimSpace(requestedTrack))
		for _, row := range mapped {
			if strings.EqualFold(row.order.TrackNumber(), norm) || strings.EqualFold(row.order.TrackNumber(), requestedTrack) {
				return order.NewCustomerSnapshot(userID, "", phone, []order.Order{a.enrichOne(ctx, userID, row)}), nil
			}
		}
		// Track may be a daigou order_sn still in China (never in delivery list).
		if dg, ok := a.findDaigouOrder(ctx, userID, requestedTrack); ok {
			return order.NewCustomerSnapshot(userID, "", phone, nil).WithDaigou([]order.Order{dg}, 1), nil
		}
	}

	snapshot := order.NewCustomerSnapshot(userID, "", phone, a.enrichRecent(ctx, userID, mapped))

	// Every other source is independent of the delivery list above and of each
	// other, so the wanted ones are fetched concurrently rather than adding
	// their latency one after another.
	var (
		wg                                                sync.WaitGroup
		dgOrders, jiyunOrders, dashOrders, unpickedOrders []order.Order
		dgTotal                                           int
	)
	run := func(source string, fetch func()) {
		if !intent.WantsSource(source) {
			return
		}
		wg.Add(1)
		go func() { defer wg.Done(); fetch() }()
	}
	if a.daigouList != nil {
		run(order.SourceDaigou, func() { dgOrders, dgTotal = a.fetchDaigou(ctx, userID) })
	}
	run(order.SourceJiyun, func() { jiyunOrders = a.fetchJiyun(ctx, userID) })
	run(order.SourceDashboard, func() { dashOrders = a.fetchDashboard(ctx, userID) })
	run(order.SourceUnpicked, func() { unpickedOrders = a.fetchUnpicked(ctx, userID) })
	wg.Wait()

	if len(dgOrders) > 0 {
		snapshot = snapshot.WithDaigou(dgOrders, dgTotal)
	}
	if len(jiyunOrders) > 0 {
		snapshot = snapshot.WithJiyun(jiyunOrders)
	}
	if len(dashOrders) > 0 {
		snapshot = snapshot.WithDashboard(dashOrders)
	}
	if len(unpickedOrders) > 0 {
		snapshot = snapshot.WithUnpicked(unpickedOrders)
	}
	// Collapse the same parcel reported by several sources, then apply the
	// question's own source/row narrowing. Dedup runs first so the filter sees
	// one row per parcel rather than counting a duplicate as a separate order.
	snapshot = order.Deduplicate(snapshot, intent)
	return order.ApplyListIntent(snapshot, intent), nil
}

// deliveryRow pairs a mapped order with the daigou order_sn its raw row
// carried. Enrichment looks the parcel up by that sn specifically, which is
// not the same field Order.TrackNumber() prefers.
type deliveryRow struct {
	order order.Order
	sn    string
}

// enrichOne fills in an order's line items from the admin API. It costs one to
// two HTTP calls, so callers decide how many orders are worth that.
func (a *CustomerAPI) enrichOne(ctx context.Context, userID int64, row deliveryRow) order.Order {
	if a.daigou == nil || !a.skuEnabled || row.sn == "" {
		return row.order
	}
	items := a.daigou.EnrichOrderItems(ctx, userID, row.sn, row.order.Items())
	if len(items) > 0 && (len(row.order.Items()) == 0 || hasRicherItems(items, row.order.Items())) {
		return row.order.WithItems(items)
	}
	return row.order
}

// enrichRecent enriches the most recent orders only, a bounded number at a
// time, and returns every order in the API's original sequence.
//
// A customer with forty parcels asking "where are my orders" does not need
// per-item photos for all forty: enriching them all was one or two admin-API
// calls per order, run one after another, which is both the slowest part of
// the answer and the heaviest load this service puts on Sahiy. Older orders
// keep whatever items the delivery list itself carried.
func (a *CustomerAPI) enrichRecent(ctx context.Context, userID int64, rows []deliveryRow) []order.Order {
	out := make([]order.Order, len(rows))
	for i, row := range rows {
		out[i] = row.order
	}
	if a.daigou == nil || !a.skuEnabled || len(rows) == 0 {
		return out
	}

	targets := mostRecentIndexes(rows, a.skuEnrichMaxOrders)
	if len(targets) < len(rows) {
		a.log.Debug("sahiy: enriching only the most recent orders",
			"enriched", len(targets), "total", len(rows), "user_id", userID)
	}

	limit := a.skuEnrichConcurrency
	if limit <= 0 {
		limit = 1
	}
	slots := make(chan struct{}, limit)
	var wg sync.WaitGroup
	for _, idx := range targets {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			slots <- struct{}{}
			defer func() { <-slots }()
			// Each goroutine owns its own index, so the shared slice needs no
			// lock.
			out[idx] = a.enrichOne(ctx, userID, rows[idx])
		}(idx)
	}
	wg.Wait()
	return out
}

// mostRecentIndexes returns the indexes of the newest max rows, in ascending
// index order. A non-positive max means every row. Rows with no creation date
// sort last: an unknown date is more likely a sparse old record than today's
// order.
func mostRecentIndexes(rows []deliveryRow, max int) []int {
	idx := make([]int, len(rows))
	for i := range rows {
		idx[i] = i
	}
	if max <= 0 || len(idx) <= max {
		return idx
	}

	sort.SliceStable(idx, func(a, b int) bool {
		ta, tb := rows[idx[a]].order.CreatedAt(), rows[idx[b]].order.CreatedAt()
		if ta.IsZero() != tb.IsZero() {
			return tb.IsZero()
		}
		return ta.After(tb)
	})
	idx = idx[:max]
	sort.Ints(idx)
	return idx
}

// fetchJiyun loads the user's in-transit (jiyun) orders.
func (a *CustomerAPI) fetchJiyun(ctx context.Context, userID int64) []order.Order {
	q := url.Values{"user": {strconv.FormatInt(userID, 10)}}
	var raw json.RawMessage
	if err := a.client.GetJSON(ctx, "/api/custom/orders", q, &raw); err != nil {
		a.log.Warn("sahiy: jiyun orders unavailable", "user_id", userID, "error", err)
		return nil
	}
	rows := extractList(raw)
	out := make([]order.Order, 0, len(rows))
	for _, row := range rows {
		out = append(out, mapJiyunRow(row))
	}
	return out
}

// fetchDashboard loads the user's pickup-branch (dashboard) orders.
func (a *CustomerAPI) fetchDashboard(ctx context.Context, userID int64) []order.Order {
	path := fmt.Sprintf("/api/client/dashboard/show/%d", userID)
	var raw json.RawMessage
	if err := a.client.GetJSON(ctx, path, nil, &raw); err != nil {
		a.log.Warn("sahiy: dashboard orders unavailable", "user_id", userID, "error", err)
		return nil
	}
	rows := extractList(raw)
	out := make([]order.Order, 0, len(rows))
	for _, row := range rows {
		out = append(out, mapDashboardRow(row))
	}
	return out
}

// fetchUnpicked loads delivery orders still awaiting pickup.
func (a *CustomerAPI) fetchUnpicked(ctx context.Context, userID int64) []order.Order {
	q := url.Values{
		"user_id":   {strconv.FormatInt(userID, 10)},
		"delivered": {"false"},
		"with[]":    {"user", "location.branch"},
	}
	var raw json.RawMessage
	if err := a.client.GetJSON(ctx, "/api/v2/admin/delivery/orders/filter", q, &raw); err != nil {
		a.log.Warn("sahiy: unpicked delivery orders unavailable", "user_id", userID, "error", err)
		return nil
	}
	rows := extractList(raw)
	out := make([]order.Order, 0, len(rows))
	for _, row := range rows {
		out = append(out, mapUnpickedRow(row))
	}
	return out
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
	return order.ReconstituteSourcedOrder(order.SourceDaigou, sn, statusCode, statusLabel, createdAt, updatedAt, items).
		WithIdentifiers(collectIdentifiers(row)...).
		WithPricing(pricingFromRow(row)).
		WithLocation(daigouLocationFromRow(row))
}

// mapRowToOrder maps a raw JSON delivery-order row to the domain model. It is
// intentionally lenient: missing or wrongly-typed fields become zero values.
func mapRowToOrder(row map[string]json.RawMessage) order.Order {
	track := rawStrFromMap(row, "track_number", "express_num", "tracking_number", "order_sn")
	statusCode := rawIntFromMap(row, "status")
	statusLabel := deliveryLabel(statusCode, "uz")
	createdAt := rawTimeFromMap(row, "created_at")
	updatedAt := rawTimeFromMap(row, "updated_at")
	return order.ReconstituteOrder(track, statusCode, statusLabel, createdAt, updatedAt, parseItemsGeneric(row)).
		WithIdentifiers(collectIdentifiers(row)...).
		WithPaymentFeeUZS(paymentFeeFromRow(row)).
		WithLocation(branchFromRow(row))
}

// pricingFromRow reads a China purchase's CNY cost breakdown. The domain
// reconciles the missing pieces (see order.NewPricing).
func pricingFromRow(row map[string]json.RawMessage) order.Pricing {
	return order.NewPricing(
		rawFloatFromMap(row, "goods_amount"),
		rawFloatFromMap(row, "freight_fee"),
		rawFloatFromMap(row, "amount"),
	)
}

// paymentFeeFromRow reads what the customer still owes on collection, in som.
// actual_payment_fee wins when present: it is the settled figure.
func paymentFeeFromRow(row map[string]json.RawMessage) float64 {
	if fee := rawFloatFromMap(row, "actual_payment_fee"); fee > 0 {
		return fee
	}
	return rawFloatFromMap(row, "payment_fee")
}

// branchFromRow reads the pickup branch a delivery row is waiting at. The
// branch may be named on the row itself or nested under "location", depending
// on whether the endpoint was asked to expand the relation.
func branchFromRow(row map[string]json.RawMessage) string {
	if name := rawStrFromMap(row, "location_number", "branch_name"); name != "" {
		return name
	}
	if loc, ok := rawObjectFromMap(row, "location"); ok {
		if name := rawStrFromMap(loc, "branch_name", "name"); name != "" {
			return name
		}
		if branch, ok := rawObjectFromMap(loc, "branch"); ok {
			return rawStrFromMap(branch, "name", "branch_name")
		}
	}
	return ""
}

// daigouLocationFromRow renders where in China a purchase currently sits.
func daigouLocationFromRow(row map[string]json.RawMessage) string {
	parts := make([]string, 0, 2)
	for _, key := range []string{"area_name", "sub_area_name"} {
		if v := strings.TrimSpace(rawStrFromMap(row, key)); v != "" {
			parts = append(parts, v)
		}
	}
	return strings.Join(parts, " - ")
}

// trackIdentifierKeys are the top-level fields a row may carry its parcel
// number in. Sahiy is inconsistent about which one is populated per endpoint,
// so all of them are collected for cross-source linking.
var trackIdentifierKeys = []string{
	"express_num", "track_number", "tracking_number",
	"order_sn", "client_order_sn", "logistics_sn", "shipment_sn", "r_order_sn", "sn",
}

// collectIdentifiers gathers every parcel number a row mentions, including the
// ones nested inside purchase_packages[] and expresses[] (where the number can
// sit on the element, on its "pivot", or on an inner "express" object). These
// nested numbers are often the only link between a purchase and the shipment
// it became.
func collectIdentifiers(row map[string]json.RawMessage) []string {
	var out []string
	add := func(s string) {
		if s != "" {
			out = append(out, s)
		}
	}
	for _, key := range trackIdentifierKeys {
		add(rawStrFromMap(row, key))
	}
	for _, pkg := range rawObjectsFromMap(row, "purchase_packages") {
		add(rawStrFromMap(pkg, "express_num"))
	}
	for _, ex := range rawObjectsFromMap(row, "expresses") {
		add(rawStrFromMap(ex, "express_num"))
		for _, nested := range []string{"pivot", "express"} {
			if obj, ok := rawObjectFromMap(ex, nested); ok {
				add(rawStrFromMap(obj, "express_num"))
			}
		}
	}
	if obj, ok := rawObjectFromMap(row, "express"); ok {
		add(rawStrFromMap(obj, "express_num"))
	}
	return out
}

// rawObjectsFromMap decodes a row field known to hold an array of objects.
func rawObjectsFromMap(m map[string]json.RawMessage, key string) []map[string]json.RawMessage {
	v, ok := m[key]
	if !ok {
		return nil
	}
	var arr []map[string]json.RawMessage
	if json.Unmarshal(v, &arr) != nil {
		return nil
	}
	return arr
}

// rawObjectFromMap decodes a row field known to hold a single object.
func rawObjectFromMap(m map[string]json.RawMessage, key string) (map[string]json.RawMessage, bool) {
	v, ok := m[key]
	if !ok {
		return nil, false
	}
	var obj map[string]json.RawMessage
	if json.Unmarshal(v, &obj) != nil {
		return nil, false
	}
	return obj, true
}

// parseItemsGeneric parses a row's "items" array using the delivery-shaped key
// set. Used by every mapper except daigou, which has its own distinct keys
// (goods_name, sku_attr, ...).
func parseItemsGeneric(row map[string]json.RawMessage) []order.OrderItem {
	rawItems, ok := row["items"]
	if !ok {
		return nil
	}
	var arr []map[string]json.RawMessage
	if json.Unmarshal(rawItems, &arr) != nil {
		return nil
	}
	items := make([]order.OrderItem, 0, len(arr))
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
	return items
}

// mapJiyunRow maps a raw JSON jiyun (in-transit logistics) order row.
func mapJiyunRow(row map[string]json.RawMessage) order.Order {
	track := rawStrFromMap(row, "track_number", "express_num", "tracking_number", "order_sn")
	statusCode := rawIntFromMap(row, "status")
	statusLabel := jiyunLabel(statusCode, "uz")
	createdAt := rawTimeFromMap(row, "created_at")
	updatedAt := rawTimeFromMap(row, "updated_at")
	return order.ReconstituteSourcedOrder(order.SourceJiyun, track, statusCode, statusLabel, createdAt, updatedAt, parseItemsGeneric(row)).
		WithIdentifiers(collectIdentifiers(row)...).
		WithPaymentFeeUZS(paymentFeeFromRow(row)).
		WithLocation(branchFromRow(row))
}

// mapDashboardRow maps a raw JSON dashboard (pickup branch) order row.
func mapDashboardRow(row map[string]json.RawMessage) order.Order {
	track := rawStrFromMap(row, "track_number", "express_num", "tracking_number", "order_sn")
	statusCode := rawIntFromMap(row, "status", "dashboard_status")
	statusLabel := dashboardLabel(statusCode, "uz")
	createdAt := rawTimeFromMap(row, "created_at")
	updatedAt := rawTimeFromMap(row, "updated_at")
	return order.ReconstituteSourcedOrder(order.SourceDashboard, track, statusCode, statusLabel, createdAt, updatedAt, parseItemsGeneric(row)).
		WithIdentifiers(collectIdentifiers(row)...).
		WithPaymentFeeUZS(paymentFeeFromRow(row)).
		WithLocation(branchFromRow(row))
}

// mapUnpickedRow maps a raw JSON unpicked-delivery order row. The shape is the
// same as a regular delivery row (it is the same endpoint, filtered), so it
// reuses mapRowToOrder and only overrides the source tag.
func mapUnpickedRow(row map[string]json.RawMessage) order.Order {
	o := mapRowToOrder(row)
	// Re-attach the identifiers: ReconstituteSourcedOrder builds a fresh value,
	// and without them this row could not be linked to its delivery twin - which
	// is exactly the duplicate this source creates.
	return order.ReconstituteSourcedOrder(order.SourceUnpicked,
		o.TrackNumber(), o.StatusCode(), o.StatusLabel(), o.CreatedAt(), o.UpdatedAt(), o.Items()).
		WithIdentifiers(collectIdentifiers(row)...).
		WithPaymentFeeUZS(o.PaymentFeeUZS()).
		WithLocation(o.Location())
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
