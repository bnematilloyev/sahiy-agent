// Package order is the bounded context for customer order/parcel data fetched
// from the Sahiy Laravel API. It contains the domain model only; no I/O.
package order

import (
	"fmt"
	"math"
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
	// SourceUnpicked tags delivery orders still awaiting pickup (a filtered
	// view of the delivery endpoint, not a separate logistics pipeline - it
	// shares the delivery status-code scale for ETA purposes).
	SourceUnpicked = "unpicked"
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
	// identifiers are the other ids the same parcel is known by across Sahiy
	// endpoints (express_num, logistics_sn, per-package numbers, ...). One
	// physical parcel appears in several sources under different ids, so
	// linking them needs all of them, not just trackNumber.
	identifiers []string
	// pricing is the CNY cost breakdown of a China purchase (daigou rows).
	pricing Pricing
	// paymentFeeUZS is what the customer still owes on collection, already in
	// som - delivery rows report it that way, so it is never rate-converted.
	paymentFeeUZS float64
	// location is where the parcel physically is: a branch name for delivery
	// rows, a China warehouse area for purchases.
	location string
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

func (o Order) Pricing() Pricing       { return o.pricing }
func (o Order) PaymentFeeUZS() float64 { return o.paymentFeeUZS }
func (o Order) Location() string       { return o.location }

// WithPricing returns a copy carrying the CNY cost breakdown.
func (o Order) WithPricing(p Pricing) Order { o.pricing = p; return o }

// WithPaymentFeeUZS returns a copy carrying the amount still due on collection.
func (o Order) WithPaymentFeeUZS(uzs float64) Order { o.paymentFeeUZS = uzs; return o }

// WithLocation returns a copy carrying the parcel's current location.
func (o Order) WithLocation(location string) Order { o.location = location; return o }

// WithItems returns a copy carrying a different line-item list, keeping every
// other field. Enrichment must go through this rather than rebuilding the
// order, which would silently drop the identifiers, pricing and location that
// the rebuild constructor knows nothing about.
func (o Order) WithItems(items []OrderItem) Order { o.items = items; return o }

// WithIdentifiers returns a copy of the order that also answers to ids, the
// alternate numbers the same parcel carries in other Sahiy endpoints.
func (o Order) WithIdentifiers(ids ...string) Order {
	o.identifiers = append(append([]string(nil), o.identifiers...), ids...)
	return o
}

// TrackKeys returns every id this order is known by, normalized for comparison
// and deduplicated. Two orders sharing any key are the same parcel.
func (o Order) TrackKeys() []string {
	seen := make(map[string]bool, len(o.identifiers)+1)
	var out []string
	for _, raw := range append([]string{o.trackNumber}, o.identifiers...) {
		key := NormalizeTrackKey(raw)
		if key == "" || seen[key] {
			continue
		}
		seen[key] = true
		out = append(out, key)
	}
	return out
}

// CustomerSnapshot is what the infra layer builds after resolving a customer query
// against the Sahiy API. Beyond delivery orders it can carry orders from other
// Sahiy sources that never appear in the delivery list: daigou (China-purchase,
// not yet shipped), jiyun (in transit), dashboard (at a pickup branch), and
// unpicked (delivery orders still awaiting pickup).
type CustomerSnapshot struct {
	userID          int64
	displayName     string
	phone           string
	orders          []Order
	daigouOrders    []Order
	daigouTotal     int
	jiyunOrders     []Order
	dashboardOrders []Order
	unpickedOrders  []Order
	// scope describes the narrowing a list question asked for, when one did.
	// It tells the model that a short list is a filtered answer rather than
	// everything the customer has.
	scope string
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

// WithJiyun returns a copy of the snapshot carrying jiyun (in-transit
// logistics) orders.
func (s CustomerSnapshot) WithJiyun(orders []Order) CustomerSnapshot {
	s.jiyunOrders = orders
	return s
}

// WithDashboard returns a copy of the snapshot carrying dashboard (pickup
// branch) orders.
func (s CustomerSnapshot) WithDashboard(orders []Order) CustomerSnapshot {
	s.dashboardOrders = orders
	return s
}

// WithUnpicked returns a copy of the snapshot carrying delivery orders still
// awaiting pickup.
func (s CustomerSnapshot) WithUnpicked(orders []Order) CustomerSnapshot {
	s.unpickedOrders = orders
	return s
}

func (s CustomerSnapshot) UserID() int64            { return s.userID }
func (s CustomerSnapshot) DisplayName() string      { return s.displayName }
func (s CustomerSnapshot) Phone() string            { return s.phone }
func (s CustomerSnapshot) Orders() []Order          { return s.orders }
func (s CustomerSnapshot) DaigouOrders() []Order    { return s.daigouOrders }
func (s CustomerSnapshot) DaigouTotal() int         { return s.daigouTotal }
func (s CustomerSnapshot) JiyunOrders() []Order     { return s.jiyunOrders }
func (s CustomerSnapshot) DashboardOrders() []Order { return s.dashboardOrders }
func (s CustomerSnapshot) UnpickedOrders() []Order  { return s.unpickedOrders }
func (s CustomerSnapshot) Scope() string            { return s.scope }

// IsEmpty reports whether no orders were found across any source.
func (s CustomerSnapshot) IsEmpty() bool {
	return len(s.orders) == 0 && len(s.daigouOrders) == 0 &&
		len(s.jiyunOrders) == 0 && len(s.dashboardOrders) == 0 && len(s.unpickedOrders) == 0
}

// Summarize renders a compact plain-text snapshot suitable for LLM context.
// The LLM rewrites this into a user-facing reply in the requested language.
// The lang parameter is accepted for future localisation of field labels but
// the current implementation uses English labels intentionally so the LLM can
// translate them freely.
//
// cnyToUZS converts China-purchase prices into som. Pass 0 when no rate is
// available: prices are then shown in CNY only, which is honest, rather than
// converted at a guessed rate.
func Summarize(s CustomerSnapshot, _ shared.Language, cnyToUZS float64) string {
	if s.IsEmpty() {
		// A scoped snapshot that came back empty is not "you have no orders" -
		// it is "none of your orders match what you asked about". Saying the
		// first would be wrong, so the distinction is made explicit here rather
		// than left for the model to infer from an empty list.
		if s.scope != "" {
			return s.scope + "\nNo orders match that. The customer may still have other orders outside this scope."
		}
		return "No orders found."
	}
	var b strings.Builder
	if s.scope != "" {
		b.WriteString(s.scope)
		b.WriteString("\nOnly matching orders are listed below.\n\n")
	}
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
		// ETA is deliberately computed here, not left to the model to guess:
		// it is a sum over a fixed days-per-stage table, and the model has no
		// way to reproduce that arithmetic reliably. English label regardless
		// of the reply language, same as the rest of this function - the LLM
		// translates it into the target language itself.
		if eta, ok := EstimateETA(o, shared.LangEn); ok {
			if eta.Delivered {
				b.WriteString("ETA: delivered\n")
			} else {
				fmt.Fprintf(&b, "ETA: ~%d days (stage: %s)\n", eta.RemainingDays, eta.StatusLabel)
			}
		}
		if o.location != "" {
			fmt.Fprintf(&b, "Location: %s\n", o.location)
		}
		// Money is computed here for the same reason as the ETA: the freight
		// fallback and the som conversion are arithmetic the model must not be
		// asked to perform on a customer's bill.
		if !o.pricing.IsZero() {
			if o.pricing.GoodsAmount() > 0 {
				fmt.Fprintf(&b, "Goods cost: %s\n", formatMoneyCNY(o.pricing.GoodsAmount(), cnyToUZS))
			}
			if o.pricing.FreightFee() > 0 {
				fmt.Fprintf(&b, "Shipping inside China: %s\n", formatMoneyCNY(o.pricing.FreightFee(), cnyToUZS))
			}
			fmt.Fprintf(&b, "Order total: %s\n", formatMoneyCNY(o.pricing.Amount(), cnyToUZS))
		}
		if o.paymentFeeUZS > 0 {
			fmt.Fprintf(&b, "Amount due on collection: %s UZS\n", FormatUZS(int64(math.Round(o.paymentFeeUZS))))
		}
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
	writeSection := func(title string, orders []Order) {
		if len(orders) == 0 {
			return
		}
		fmt.Fprintf(&b, "\n=== %s: %d ===\n", title, len(orders))
		for _, o := range orders {
			writeOrder(o)
		}
	}
	writeSection("In transit (jiyun) orders", s.jiyunOrders)
	writeSection("At pickup branch (dashboard) orders", s.dashboardOrders)
	writeSection("Awaiting pickup orders", s.unpickedOrders)
	return b.String()
}
