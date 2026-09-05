package order

import "strings"

// One physical parcel is reported by several Sahiy endpoints at once. A China
// purchase becomes a logistics shipment, which becomes a delivery row, which -
// while it is still uncollected - is also returned by the "not delivered"
// filter. Listing each of those as its own order tells the customer they have
// four parcels when they have one.
//
// Linking them is deterministic set work over identifiers, done before the
// model ever sees the data: given a flattened list the model has no reliable
// way to tell "same parcel, two sources" from "two parcels".

// daigouPurchaseMaxStatus is the last daigou status that still means "in the
// purchase phase". Status 6 hands the parcel to logistics, from which point it
// is represented by a jiyun/delivery row instead.
const daigouPurchaseMaxStatus = 5

// NormalizeTrackKey reduces a tracking number to a comparable key: spaces,
// dashes and underscores dropped, upper-cased. "sf-123 456" and "SF123456"
// are the same parcel.
func NormalizeTrackKey(raw string) string {
	var b strings.Builder
	b.Grow(len(raw))
	for _, r := range strings.TrimSpace(raw) {
		switch r {
		case ' ', '\t', '-', '_':
			continue
		}
		b.WriteRune(r)
	}
	return strings.ToUpper(b.String())
}

// ShouldChain reports whether a question's intent allows the purchase-phase
// narrowing below.
//
// It must not apply to questions that deliberately ask for orders outside the
// purchase phase: "show my cancelled orders" wants daigou status 10/11, which
// the narrowing would throw away. Duplicate removal itself is always safe and
// is not gated on this.
func ShouldChain(intent ListIntent) bool {
	switch intent.RowFilter() {
	case FilterPendingArrival, FilterActive, FilterCompleted:
		return true
	case FilterNone:
		return len(intent.sources) == len(allSources)
	default:
		return false
	}
}

// dedupePriority lists the sources from most to least informative. When the
// same parcel turns up more than once, the copy from the earliest source here
// is the one kept: jiyun carries the live logistics status, unpicked adds the
// branch it is waiting at, delivery is the plain row, and dashboard/daigou
// only restate what the others already say.
var dedupePriority = []string{SourceJiyun, SourceUnpicked, SourceDelivery, SourceDashboard, SourceDaigou}

// Deduplicate collapses a snapshot so each physical parcel appears once.
//
// Two things happen. First, when the intent allows it (see ShouldChain),
// daigou rows past the purchase phase are dropped: that parcel has moved on to
// logistics and is already listed there. Second, any remaining row whose
// identifiers match one already kept from a higher-priority source is removed.
func Deduplicate(s CustomerSnapshot, intent ListIntent) CustomerSnapshot {
	bySource := map[string][]Order{
		SourceJiyun:     s.jiyunOrders,
		SourceUnpicked:  s.unpickedOrders,
		SourceDelivery:  s.orders,
		SourceDashboard: s.dashboardOrders,
		SourceDaigou:    s.daigouOrders,
	}

	if ShouldChain(intent) {
		bySource[SourceDaigou] = keepPurchasePhase(bySource[SourceDaigou])
	}

	claimed := make(map[string]bool)
	for _, source := range dedupePriority {
		bySource[source] = keepUnclaimed(bySource[source], claimed)
	}

	out := s
	out.jiyunOrders = bySource[SourceJiyun]
	out.unpickedOrders = bySource[SourceUnpicked]
	out.orders = bySource[SourceDelivery]
	out.dashboardOrders = bySource[SourceDashboard]
	if len(bySource[SourceDaigou]) != len(s.daigouOrders) {
		out.daigouTotal = len(bySource[SourceDaigou])
	}
	out.daigouOrders = bySource[SourceDaigou]
	return out
}

// keepPurchasePhase drops daigou rows that have already been handed to
// logistics, where they are represented by a jiyun or delivery row instead.
func keepPurchasePhase(orders []Order) []Order {
	out := make([]Order, 0, len(orders))
	for _, o := range orders {
		if o.StatusCode() <= daigouPurchaseMaxStatus {
			out = append(out, o)
		}
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

// keepUnclaimed returns the orders whose identifiers no higher-priority source
// has claimed yet, claiming the survivors' keys as it goes.
//
// An order with no usable identifier at all cannot be matched against anything,
// so it is kept: dropping it would silently lose a real parcel, while keeping
// it risks at worst showing one twice.
func keepUnclaimed(orders []Order, claimed map[string]bool) []Order {
	out := make([]Order, 0, len(orders))
	for _, o := range orders {
		keys := o.TrackKeys()
		if anyClaimed(keys, claimed) {
			continue
		}
		for _, k := range keys {
			claimed[k] = true
		}
		out = append(out, o)
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

func anyClaimed(keys []string, claimed map[string]bool) bool {
	for _, k := range keys {
		if claimed[k] {
			return true
		}
	}
	return false
}
