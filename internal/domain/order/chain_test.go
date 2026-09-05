package order

import (
	"testing"
	"time"
)

func TestNormalizeTrackKey(t *testing.T) {
	cases := map[string]string{
		"sf-123 456": "SF123456",
		" SF123456 ": "SF123456",
		"sf_123-456": "SF123456",
		"":           "",
		"   ":        "",
		"DG00012345": "DG00012345",
	}
	for in, want := range cases {
		if got := NormalizeTrackKey(in); got != want {
			t.Errorf("NormalizeTrackKey(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestOrderTrackKeysIncludesIdentifiers(t *testing.T) {
	o := ReconstituteOrder("TRK-1", 1, "", time.Time{}, time.Time{}, nil).
		WithIdentifiers("exp 1", "TRK1", "")

	got := o.TrackKeys()
	want := map[string]bool{"TRK1": true, "EXP1": true}
	if len(got) != len(want) {
		t.Fatalf("TrackKeys() = %v, want %d distinct keys", got, len(want))
	}
	for _, k := range got {
		if !want[k] {
			t.Errorf("unexpected key %q in %v", k, got)
		}
	}
}

func TestShouldChain(t *testing.T) {
	cases := []struct {
		query string
		want  bool
	}{
		{"buyurtmalarim", true},                 // default intent
		{"aktiv buyurtmalarim", true},           // active
		{"yakunlangan buyurtmalar", true},       // completed
		{"bekor qilingan buyurtmalarim", false}, // cancelled must keep daigou 10/11
		{"buyurtmam kelmayapti", false},         // delayed
		{"xitoyda turgan buyurtmalarim", false}, // in_china keeps the purchase rows as-is
	}
	for _, c := range cases {
		if got := ShouldChain(ParseListIntent(c.query)); got != c.want {
			t.Errorf("ShouldChain(%q) = %v, want %v", c.query, got, c.want)
		}
	}
}

// The unpicked endpoint returns a subset of the delivery list, so the same
// parcel arrives twice. It must be reported once.
func TestDeduplicateCollapsesDeliveryAndUnpickedTwins(t *testing.T) {
	snap := NewCustomerSnapshot(1, "", "", []Order{
		ReconstituteOrder("SF-123 456", 4, "at station", time.Time{}, time.Time{}, nil),
		ReconstituteOrder("OTHER-9", 3, "in transit", time.Time{}, time.Time{}, nil),
	}).WithUnpicked([]Order{
		// Same parcel, written differently by the other endpoint.
		ReconstituteSourcedOrder(SourceUnpicked, "sf123456", 4, "awaiting pickup", time.Time{}, time.Time{}, nil),
	})

	out := Deduplicate(snap, DefaultListIntent())

	if len(out.UnpickedOrders()) != 1 {
		t.Fatalf("unpicked should win the duplicate, got %+v", out.UnpickedOrders())
	}
	if len(out.Orders()) != 1 || out.Orders()[0].TrackNumber() != "OTHER-9" {
		t.Fatalf("delivery should keep only the parcel with no twin, got %+v", out.Orders())
	}
}

// A daigou purchase that has been handed to logistics is already listed as a
// jiyun row; keeping both would show one parcel as two.
func TestDeduplicateDropsDaigouAlreadyShipped(t *testing.T) {
	snap := NewCustomerSnapshot(1, "", "", nil).
		WithJiyun([]Order{
			ReconstituteSourcedOrder(SourceJiyun, "SF999", 3, "", time.Time{}, time.Time{}, nil),
		}).
		WithDaigou([]Order{
			// Still in the purchase phase and linked to the shipment above.
			ReconstituteSourcedOrder(SourceDaigou, "DG1", 5, "", time.Time{}, time.Time{}, nil).
				WithIdentifiers("SF-999"),
			// Unrelated purchase, must survive.
			ReconstituteSourcedOrder(SourceDaigou, "DG2", 2, "", time.Time{}, time.Time{}, nil),
		}, 2)

	out := Deduplicate(snap, DefaultListIntent())

	if len(out.DaigouOrders()) != 1 || out.DaigouOrders()[0].TrackNumber() != "DG2" {
		t.Fatalf("daigou = %+v, want only DG2", out.DaigouOrders())
	}
	if out.DaigouTotal() != 1 {
		t.Errorf("DaigouTotal = %d, want it corrected to 1", out.DaigouTotal())
	}
	if len(out.JiyunOrders()) != 1 {
		t.Errorf("the jiyun row must be kept, got %+v", out.JiyunOrders())
	}
}

// Status 6+ means the parcel left the purchase phase, so it is dropped even
// when no matching shipment row was fetched.
func TestDeduplicateDropsDaigouPastPurchasePhase(t *testing.T) {
	snap := NewCustomerSnapshot(1, "", "", nil).WithDaigou([]Order{
		ReconstituteSourcedOrder(SourceDaigou, "DG-SHIPPED", 6, "", time.Time{}, time.Time{}, nil),
		ReconstituteSourcedOrder(SourceDaigou, "DG-BUYING", 3, "", time.Time{}, time.Time{}, nil),
	}, 2)

	out := Deduplicate(snap, DefaultListIntent())

	if len(out.DaigouOrders()) != 1 || out.DaigouOrders()[0].TrackNumber() != "DG-BUYING" {
		t.Fatalf("daigou = %+v, want only DG-BUYING", out.DaigouOrders())
	}
}

// The purchase-phase narrowing must not fire for a question that deliberately
// asks for orders outside it, or "show my cancelled orders" returns nothing.
func TestDeduplicateKeepsCancelledDaigouForCancelledQuestion(t *testing.T) {
	snap := NewCustomerSnapshot(1, "", "", nil).WithDaigou([]Order{
		ReconstituteSourcedOrder(SourceDaigou, "DG-CANCELLED", 10, "", time.Time{}, time.Time{}, nil),
	}, 1)

	out := Deduplicate(snap, ParseListIntent("bekor qilingan buyurtmalarim"))

	if len(out.DaigouOrders()) != 1 {
		t.Fatalf("a cancelled-scoped question must keep daigou 10/11, got %+v", out.DaigouOrders())
	}
}

// Duplicate removal is unconditional, so it still applies to a question whose
// intent switches the purchase-phase narrowing off.
func TestDeduplicateRemovesDuplicatesEvenWhenChainingOff(t *testing.T) {
	snap := NewCustomerSnapshot(1, "", "", []Order{
		ReconstituteOrder("SF1", 4, "", time.Time{}, time.Time{}, nil),
	}).WithUnpicked([]Order{
		ReconstituteSourcedOrder(SourceUnpicked, "SF1", 4, "", time.Time{}, time.Time{}, nil),
	})

	intent := ParseListIntent("buyurtmam kelmayapti") // delayed -> ShouldChain false
	if ShouldChain(intent) {
		t.Fatal("precondition: the delayed intent should disable chaining")
	}

	out := Deduplicate(snap, intent)
	if len(out.Orders())+len(out.UnpickedOrders()) != 1 {
		t.Fatalf("the parcel must still be listed once, got %d delivery + %d unpicked",
			len(out.Orders()), len(out.UnpickedOrders()))
	}
}

// An order carrying no usable identifier cannot be matched, so it is kept
// rather than silently dropped.
func TestDeduplicateKeepsOrdersWithoutIdentifiers(t *testing.T) {
	snap := NewCustomerSnapshot(1, "", "", []Order{
		ReconstituteOrder("", 3, "no id", time.Time{}, time.Time{}, nil),
		ReconstituteOrder("", 4, "also no id", time.Time{}, time.Time{}, nil),
	})

	out := Deduplicate(snap, DefaultListIntent())

	if len(out.Orders()) != 2 {
		t.Fatalf("orders without identifiers must all be kept, got %d", len(out.Orders()))
	}
}
