// Package order is the bounded context for customer order/parcel data fetched
// from the Sahiy Laravel API. It contains the domain model only; no I/O.
package order

import (
	"fmt"
	"strings"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// OrderItem is a single line item within an order.
type OrderItem struct {
	name      string
	sku       string
	quantity  int
	unitPrice float64
	currency  string
	imageURL  string
}

// NewOrderItem constructs an OrderItem value object.
func NewOrderItem(name, sku string, quantity int, unitPrice float64, currency, imageURL string) OrderItem {
	return OrderItem{
		name:      name,
		sku:       sku,
		quantity:  quantity,
		unitPrice: unitPrice,
		currency:  currency,
		imageURL:  imageURL,
	}
}

func (i OrderItem) Name() string       { return i.name }
func (i OrderItem) SKU() string        { return i.sku }
func (i OrderItem) Quantity() int      { return i.quantity }
func (i OrderItem) UnitPrice() float64 { return i.unitPrice }
func (i OrderItem) Currency() string   { return i.currency }
func (i OrderItem) ImageURL() string   { return i.imageURL }

// Order source tags identify which Sahiy endpoint a row came from.
const (
	SourceDelivery  = "delivery"
	SourceDaigou    = "daigou"
	SourceJiyun     = "jiyun"
	SourceDashboard = "dashboard"
)

// Order represents a single delivery/parcel record from the Sahiy API.
type Order struct {
	trackNumber string
	statusCode  int
	statusLabel string
	source      string
	createdAt   time.Time
	updatedAt   time.Time
	items       []OrderItem
}

// ReconstituteOrder is the infra-layer constructor. Domain logic does not
// create Orders from scratch; only the infra adapter does after mapping API JSON.
func ReconstituteOrder(
	trackNumber string,
	statusCode int,
	statusLabel string,
	createdAt, updatedAt time.Time,
	items []OrderItem,
) Order {
	return Order{
		trackNumber: trackNumber,
		statusCode:  statusCode,
		statusLabel: statusLabel,
		source:      SourceDelivery,
		createdAt:   createdAt,
		updatedAt:   updatedAt,
		items:       items,
	}
}

// ReconstituteSourcedOrder is like ReconstituteOrder but tags the order with its
// originating source (daigou, jiyun, dashboard, delivery).
func ReconstituteSourcedOrder(
	source string,
	trackNumber string,
	statusCode int,
	statusLabel string,
	createdAt, updatedAt time.Time,
	items []OrderItem,
) Order {
	o := ReconstituteOrder(trackNumber, statusCode, statusLabel, createdAt, updatedAt, items)
	o.source = source
	return o
}

func (o Order) TrackNumber() string  { return o.trackNumber }
func (o Order) StatusCode() int      { return o.statusCode }
func (o Order) StatusLabel() string  { return o.statusLabel }
func (o Order) Source() string       { return o.source }
func (o Order) CreatedAt() time.Time { return o.createdAt }
func (o Order) UpdatedAt() time.Time { return o.updatedAt }
func (o Order) Items() []OrderItem   { return o.items }

// CustomerSnapshot is what the infra layer builds after resolving a customer query
// against the Sahiy API. Beyond delivery orders it can carry China-purchase
// (daigou) orders which have not yet shipped and so never appear in delivery.
type CustomerSnapshot struct {
	userID       int64
	displayName  string
	phone        string
	orders       []Order
	daigouOrders []Order
	daigouTotal  int
}

// NewCustomerSnapshot constructs a CustomerSnapshot value object.
func NewCustomerSnapshot(userID int64, displayName, phone string, orders []Order) CustomerSnapshot {
	return CustomerSnapshot{
		userID:      userID,
		displayName: displayName,
		phone:       phone,
		orders:      orders,
	}
}

// WithDaigou returns a copy of the snapshot carrying daigou (China purchase)
// orders and the server-reported total count.
func (s CustomerSnapshot) WithDaigou(orders []Order, total int) CustomerSnapshot {
	s.daigouOrders = orders
	s.daigouTotal = total
	return s
}

func (s CustomerSnapshot) UserID() int64           { return s.userID }
func (s CustomerSnapshot) DisplayName() string     { return s.displayName }
func (s CustomerSnapshot) Phone() string           { return s.phone }
func (s CustomerSnapshot) Orders() []Order         { return s.orders }
func (s CustomerSnapshot) DaigouOrders() []Order   { return s.daigouOrders }
func (s CustomerSnapshot) DaigouTotal() int        { return s.daigouTotal }

// IsEmpty reports whether no orders were found across any source (no user
// identified, or the user has no delivery and no daigou orders).
func (s CustomerSnapshot) IsEmpty() bool { return len(s.orders) == 0 && len(s.daigouOrders) == 0 }

// Summarize renders a compact plain-text snapshot suitable for LLM context.
// The LLM rewrites this into a user-facing reply in the requested language.
// The lang parameter is accepted for future localisation of field labels but
// the current implementation uses English labels intentionally so the LLM can
// translate them freely.
func Summarize(s CustomerSnapshot, _ shared.Language) string {
	if s.IsEmpty() {
		return "No orders found."
	}
	var b strings.Builder
	written := 0
	writeOrder := func(o Order) {
		if written > 0 {
			b.WriteString("\n---\n")
		}
		written++
		if o.source == SourceDaigou {
			fmt.Fprintf(&b, "Order SN: %s (China purchase / daigou)\n", o.trackNumber)
		} else {
			fmt.Fprintf(&b, "Track: %s\n", o.trackNumber)
		}
		fmt.Fprintf(&b, "Status: %s\n", o.statusLabel)
		if !o.createdAt.IsZero() {
			fmt.Fprintf(&b, "Created: %s\n", o.createdAt.Format("2006-01-02"))
		}
		if !o.updatedAt.IsZero() {
			fmt.Fprintf(&b, "Updated: %s\n", o.updatedAt.Format("2006-01-02"))
		}
		for _, item := range o.items {
			fmt.Fprintf(&b, "  - %s", item.name)
			if item.sku != "" {
				fmt.Fprintf(&b, " [SKU: %s]", item.sku)
			}
			if item.quantity > 0 {
				fmt.Fprintf(&b, " x%d", item.quantity)
			}
			if item.unitPrice > 0 {
				fmt.Fprintf(&b, " %.2f %s", item.unitPrice, item.currency)
			}
			if item.imageURL != "" {
				fmt.Fprintf(&b, " (img: %s)", item.imageURL)
			}
			b.WriteByte('\n')
		}
	}
	for _, o := range s.orders {
		writeOrder(o)
	}
	if len(s.daigouOrders) > 0 {
		fmt.Fprintf(&b, "\n=== China purchase (daigou) orders: %d ===\n", s.daigouTotal)
		for _, o := range s.daigouOrders {
			writeOrder(o)
		}
	}
	return b.String()
}
