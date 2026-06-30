package sahiy

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/url"
	"strconv"
	"strings"
)

// Faithful port of app/infrastructure/sahiy_api/daigou.py — listing China
// purchase (daigou) orders up to the warehouse stage.

const (
	daigouAnalyticsPath = "/api/v2/admin/delivery/orders/analytics/daigou"
	customDaigouPath    = "/api/custom-daigou-orders/"
)

// daigouHandoffStatus (6 = "in transit") never appears in the daigou list — such
// an order has moved on to jiyun/delivery. Kept for parity with the Python docs.
const daigouHandoffStatus = 6

// daigouPurchaseStatuses are the codes still "in China" (purchase lifecycle).
var daigouPurchaseStatuses = []int{0, 1, 2, 3, 4, 5}

var daigouIntentStatusMap = map[string][]int{
	"active":          {1, 2, 3, 4, 5},
	"pending_arrival": {1, 2, 3, 4, 5},
	"cancelled":       {10, 11},
	"completed":       {6},
	"in_china":        {0, 1, 2, 3, 4, 5},
}

// intentStatusCodes returns the daigou status codes to request for a list
// filter. useFilter=false means the intent is unknown and the caller should hit
// the analytics endpoint (all statuses), mirroring Python's None sentinel.
func intentStatusCodes(rowFilter string) (codes []int, useFilter bool) {
	if rowFilter == "" {
		return append([]int(nil), daigouPurchaseStatuses...), true
	}
	if c, ok := daigouIntentStatusMap[rowFilter]; ok {
		return append([]int(nil), c...), true
	}
	return nil, false
}

type daigouPage struct {
	items   []map[string]json.RawMessage
	current int
	last    int
}

// extractDaigouPage parses the analytics endpoint shape: body.data.data is the
// item list, with pagination in body.data.{current_page,last_page}.
func extractDaigouPage(raw json.RawMessage) daigouPage {
	obj, ok := objFromRaw(raw)
	if !ok {
		return daigouPage{current: 1, last: 1}
	}
	dataObj, ok := objFromRaw(obj["data"])
	if !ok {
		return daigouPage{current: 1, last: 1}
	}
	items := listFromRaw(dataObj["data"])
	current := rawIntFromMap(dataObj, "current_page")
	if current == 0 {
		current = 1
	}
	last := rawIntFromMap(dataObj, "last_page")
	if last == 0 {
		last = 1
	}
	return daigouPage{items: items, current: current, last: last}
}

// extractCustomPage parses the /api/custom-daigou-orders/ shape, tolerating the
// analytics nested form, a flat "data" list, or an "orders" list.
func extractCustomPage(raw json.RawMessage) daigouPage {
	obj, ok := objFromRaw(raw)
	if !ok {
		return daigouPage{current: 1, last: 1}
	}
	// Analytics-style nested first.
	if dataObj, ok := objFromRaw(obj["data"]); ok {
		if _, hasInner := dataObj["data"]; hasInner {
			return extractDaigouPage(raw)
		}
	}
	if items := listFromRaw(obj["data"]); len(items) > 0 {
		return daigouPage{items: items, current: 1, last: 1}
	}
	if items := listFromRaw(obj["orders"]); len(items) > 0 {
		return daigouPage{items: items, current: 1, last: 1}
	}
	for _, key := range []string{"data", "result", "items"} {
		if items := listFromRaw(obj[key]); len(items) > 0 {
			return daigouPage{items: items, current: 1, last: 1}
		}
		if inner, ok := objFromRaw(obj[key]); ok {
			if items := listFromRaw(inner["data"]); len(items) > 0 {
				current := rawIntFromMap(inner, "current_page")
				if current == 0 {
					current = 1
				}
				last := rawIntFromMap(inner, "last_page")
				if last == 0 {
					last = 1
				}
				return daigouPage{items: items, current: current, last: last}
			}
		}
	}
	return daigouPage{current: 1, last: 1}
}

// fetchDaigouOrders returns daigou orders for a user. When useFilter is true it
// uses the custom endpoint with server-side status[] filtering, falling back to
// the analytics endpoint on error. When false it uses analytics (all statuses).
func (a *DaigouList) fetchDaigouOrders(ctx context.Context, userID int64, page, size int, statusCodes []int, useFilter bool) (items []map[string]json.RawMessage, total int) {
	if useFilter {
		return a.fetchCustom(ctx, userID, page, size, statusCodes)
	}
	q := url.Values{}
	q.Set("user_id", strconv.FormatInt(userID, 10))
	q.Set("page", strconv.Itoa(page))
	q.Set("size", strconv.Itoa(size))
	var raw json.RawMessage
	if err := a.client.GetJSON(ctx, daigouAnalyticsPath, q, &raw); err != nil {
		a.log.Warn("daigou: analytics fetch failed", "user_id", userID, "error", err)
		return nil, 0
	}
	pg := extractDaigouPage(raw)
	return pg.items, daigouTotal(raw, len(pg.items))
}

func (a *DaigouList) fetchCustom(ctx context.Context, userID int64, page, size int, statusCodes []int) (items []map[string]json.RawMessage, total int) {
	q := url.Values{}
	q.Set("user_id", strconv.FormatInt(userID, 10))
	q.Set("page", strconv.Itoa(page))
	q.Set("size", strconv.Itoa(size))
	for _, code := range statusCodes {
		q.Add("status[]", strconv.Itoa(code))
	}
	var raw json.RawMessage
	if err := a.client.GetJSON(ctx, customDaigouPath, q, &raw); err != nil {
		a.log.Warn("daigou: custom endpoint failed, falling back to analytics", "status", statusCodes, "error", err)
		fq := url.Values{}
		fq.Set("user_id", strconv.FormatInt(userID, 10))
		fq.Set("page", strconv.Itoa(page))
		fq.Set("size", strconv.Itoa(size))
		var fraw json.RawMessage
		if err := a.client.GetJSON(ctx, daigouAnalyticsPath, fq, &fraw); err != nil {
			return nil, 0
		}
		pg := extractDaigouPage(fraw)
		return pg.items, daigouTotal(fraw, len(pg.items))
	}
	pg := extractCustomPage(raw)
	return pg.items, customDaigouTotal(raw, len(pg.items))
}

// findDaigouBySN scans analytics pages for an order matching order_sn.
func (a *DaigouList) findDaigouBySN(ctx context.Context, userID int64, orderSN string, pageSize, maxPages int) (map[string]json.RawMessage, bool) {
	target := strings.ToUpper(strings.TrimSpace(orderSN))
	if target == "" {
		return nil, false
	}
	if pageSize <= 0 {
		pageSize = 50
	}
	if maxPages <= 0 {
		maxPages = 5
	}
	for page := 1; page <= maxPages; page++ {
		q := url.Values{}
		q.Set("user_id", strconv.FormatInt(userID, 10))
		q.Set("page", strconv.Itoa(page))
		q.Set("size", strconv.Itoa(pageSize))
		var raw json.RawMessage
		if err := a.client.GetJSON(ctx, daigouAnalyticsPath, q, &raw); err != nil {
			a.log.Warn("daigou: find-by-sn page failed", "page", page, "error", err)
			return nil, false
		}
		pg := extractDaigouPage(raw)
		for _, row := range pg.items {
			if strings.EqualFold(strings.TrimSpace(rawStrFromMap(row, "order_sn")), target) {
				return row, true
			}
		}
		if page >= pg.last {
			break
		}
	}
	a.log.Info("daigou: order_sn not found", "order_sn", target, "user_id", userID)
	return nil, false
}

// daigouTotal mirrors the analytics total resolution: data.total or top-level
// count, else the item count.
func daigouTotal(raw json.RawMessage, itemCount int) int {
	obj, ok := objFromRaw(raw)
	if !ok {
		return itemCount
	}
	if dataObj, ok := objFromRaw(obj["data"]); ok {
		if t := rawIntFromMap(dataObj, "total"); t != 0 {
			return t
		}
		if t := rawIntFromMap(obj, "count"); t != 0 {
			return t
		}
		return itemCount
	}
	if t := rawIntFromMap(obj, "count"); t != 0 {
		return t
	}
	return itemCount
}

// customDaigouTotal mirrors the custom endpoint total resolution.
func customDaigouTotal(raw json.RawMessage, itemCount int) int {
	obj, ok := objFromRaw(raw)
	if !ok {
		return itemCount
	}
	for _, key := range []string{"total", "count"} {
		if t := rawIntFromMap(obj, key); t != 0 {
			return t
		}
	}
	if dataObj, ok := objFromRaw(obj["data"]); ok {
		if t := rawIntFromMap(dataObj, "total"); t != 0 {
			return t
		}
	}
	return itemCount
}

// DaigouList fetches daigou (China purchase) order lists.
type DaigouList struct {
	client *Client
	log    *slog.Logger
}

// NewDaigouList constructs the daigou list client.
func NewDaigouList(client *Client, log *slog.Logger) *DaigouList {
	return &DaigouList{client: client, log: log}
}

// --- raw JSON helpers ------------------------------------------------------

func objFromRaw(raw json.RawMessage) (map[string]json.RawMessage, bool) {
	if len(raw) == 0 {
		return nil, false
	}
	var obj map[string]json.RawMessage
	if json.Unmarshal(raw, &obj) != nil || obj == nil {
		return nil, false
	}
	return obj, true
}

func listFromRaw(raw json.RawMessage) []map[string]json.RawMessage {
	if len(raw) == 0 {
		return nil
	}
	var arr []map[string]json.RawMessage
	if json.Unmarshal(raw, &arr) != nil {
		return nil
	}
	return arr
}
