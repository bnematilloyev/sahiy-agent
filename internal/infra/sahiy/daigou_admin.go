package sahiy

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/url"
	"strconv"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/order"
)

const daigouOrderPath = "/api/admin/daigou-orders/"

// DaigouAdmin fetches rich SKU details from the admin daigou API.
type DaigouAdmin struct {
	client *AdminClient
	log    *slog.Logger
}

// NewDaigouAdmin constructs the daigou admin client.
func NewDaigouAdmin(client *AdminClient, log *slog.Logger) *DaigouAdmin {
	return &DaigouAdmin{client: client, log: log}
}

// EnrichOrderItems tries to load SKU rows for a delivery order and returns
// enriched line items. When admin lookup fails, the original items are returned.
func (d *DaigouAdmin) EnrichOrderItems(ctx context.Context, userID int64, orderSN string, existing []order.OrderItem) []order.OrderItem {
	if d == nil || d.client == nil || userID == 0 {
		return existing
	}
	sn := strings.ToUpper(strings.TrimSpace(orderSN))
	if sn == "" {
		return existing
	}
	if items := d.fetchBySN(ctx, userID, sn); len(items) > 0 {
		return items
	}
	return existing
}

func (d *DaigouAdmin) fetchByID(ctx context.Context, orderID int64) []order.OrderItem {
	var raw json.RawMessage
	ok, err := d.client.GetJSON(ctx, daigouOrderPath+strconv.FormatInt(orderID, 10), nil, &raw)
	if err != nil {
		d.log.Debug("daigou: fetch by id failed", "order_id", orderID, "error", err)
		return nil
	}
	if !ok {
		return nil
	}
	row := extractSingleOrder(raw)
	if row == nil {
		return nil
	}
	return mapDaigouSKUs(row)
}

func (d *DaigouAdmin) fetchBySN(ctx context.Context, userID int64, orderSN string) []order.OrderItem {
	q := url.Values{
		"user_id":  {strconv.FormatInt(userID, 10)},
		"order_sn": {orderSN},
		"size":     {"5"},
	}
	var raw json.RawMessage
	ok, err := d.client.GetJSON(ctx, daigouOrderPath, q, &raw)
	if err != nil {
		d.log.Debug("daigou: fetch by sn failed", "order_sn", orderSN, "error", err)
		return nil
	}
	if !ok {
		return nil
	}
	target := strings.ToUpper(strings.TrimSpace(orderSN))
	for _, row := range extractList(raw) {
		sn := strings.ToUpper(rawStrFromMap(row, "order_sn"))
		if sn != target {
			continue
		}
		if id := rawInt64FromMap(row, "id"); id > 0 {
			if items := d.fetchByID(ctx, id); len(items) > 0 {
				return items
			}
		}
		return mapDaigouSKUs(row)
	}
	return nil
}

func mapDaigouSKUs(row map[string]json.RawMessage) []order.OrderItem {
	rawSKUs, ok := row["skus"]
	if !ok {
		return nil
	}
	var arr []map[string]json.RawMessage
	if json.Unmarshal(rawSKUs, &arr) != nil {
		return nil
	}
	out := make([]order.OrderItem, 0, len(arr))
	for _, skuRow := range arr {
		item := mapOneSKU(skuRow)
		if item.Name() == "" {
			continue
		}
		out = append(out, item)
	}
	return out
}

func mapOneSKU(row map[string]json.RawMessage) order.OrderItem {
	skuInfo := nestedMap(row, "sku_info")
	name := rawStrFromMap(row, "name")
	if name == "" && skuInfo != nil {
		name = rawStrFromMap(skuInfo, "name")
	}
	qty := rawIntFromMap(row, "quantity")
	if qty <= 0 {
		qty = 1
	}
	price := money(rawFloatFromMap(row, "actual_price"))
	if price <= 0 {
		price = money(rawFloatFromMap(row, "price"))
	}
	img := firstImage(row, skuInfo)
	platformSKU := rawStrFromMap(row, "platform_sku")
	return order.NewOrderItem(name, platformSKU, qty, price, "CNY", img)
}

func nestedMap(row map[string]json.RawMessage, key string) map[string]json.RawMessage {
	v, ok := row[key]
	if !ok {
		return nil
	}
	var obj map[string]json.RawMessage
	if json.Unmarshal(v, &obj) != nil {
		return nil
	}
	return obj
}

func firstImage(row map[string]json.RawMessage, skuInfo map[string]json.RawMessage) string {
	for _, src := range []map[string]json.RawMessage{skuInfo, row} {
		if src == nil {
			continue
		}
		if img := rawStrFromMap(src, "sku_img", "image", "thumb"); img != "" {
			return img
		}
		if raw, ok := src["imgs"]; ok {
			var imgs []string
			if json.Unmarshal(raw, &imgs) == nil {
				for _, u := range imgs {
					if u != "" {
						return u
					}
				}
			}
		}
	}
	return ""
}

// money converts API fen-style integers to decimal CNY when needed.
func money(raw float64) float64 {
	if raw == 0 {
		return 0
	}
	if raw >= 100 && raw == float64(int64(raw)) {
		return raw / 100
	}
	return raw
}
