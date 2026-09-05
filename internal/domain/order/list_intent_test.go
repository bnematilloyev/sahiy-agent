package order

import (
	"strings"
	"testing"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

func TestParseListIntentRowFilter(t *testing.T) {
	cases := []struct {
		name  string
		query string
		want  RowFilter
	}{
		{"uzbek cancelled", "bekor qilingan buyurtmalarim", FilterCancelled},
		{"russian cancelled", "покажи отменённые заказы", FilterCancelled},
		{"uzbek active", "aktiv buyurtmalarim", FilterActive},
		{"russian active", "мои активные заказы", FilterActive},
		{"russian current", "текущие заказы", FilterActive},
		{"uzbek delayed", "buyurtmam kelmayapti", FilterDelayed},
		{"russian delayed", "задержка посылки", FilterDelayed},
		{"uzbek arrival", "buyurtmam qachon keladi", FilterPendingArrival},
		{"russian arrival", "когда придет мой заказ", FilterPendingArrival},
		{"english arrival", "when will my order arrive", FilterPendingArrival},
		{"uzbek completed", "yakunlangan buyurtmalar", FilterCompleted},
		{"russian completed", "полученные заказы", FilterCompleted},
		{"in china", "xitoyda turgan buyurtmalarim", FilterInChina},
		{"where are my orders", "buyurtmalarim qayerda", FilterActive},
		{"russian where", "где мои заказы", FilterActive},
		{"plain question", "salom, narxlar qanday", FilterNone},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := ParseListIntent(c.query).RowFilter(); got != c.want {
				t.Errorf("ParseListIntent(%q).RowFilter() = %q, want %q", c.query, got, c.want)
			}
		})
	}
}

// The Cyrillic keyword lists must actually match Cyrillic input. Writing them
// pre-transliterated (as the Python original did) silently fails against this
// codebase's normalizer, so these cases guard specifically the words whose
// transliteration differs between the two: ж->j, х->x, й->y, щ->sh.
func TestParseListIntentMatchesCyrillicWithDivergentTransliteration(t *testing.T) {
	cases := []struct {
		query string
		want  RowFilter
	}{
		{"задержка заказа", FilterDelayed}, // ж -> j, not zh
		{"не приехало", FilterDelayed},     // х -> x, not kh
		{"текущие заказы", FilterActive},   // щ -> sh, not shch
	}
	for _, c := range cases {
		if got := ParseListIntent(c.query).RowFilter(); got != c.want {
			t.Errorf("ParseListIntent(%q).RowFilter() = %q, want %q (normalized: %q)",
				c.query, got, c.want, shared.NormalizeForMatch(c.query))
		}
	}
	// "китай" -> "kitay" (й -> y), which must select the daigou source.
	if got := ParseListIntent("заказы из Китая"); !got.WantsSource(SourceDaigou) {
		t.Errorf("Russian 'из Китая' did not select the daigou source; sources=%v", got.Sources())
	}
}

func TestParseListIntentSources(t *testing.T) {
	// Naming a source narrows to it alone.
	got := ParseListIntent("daigou buyurtmalarim")
	if !got.WantsSource(SourceDaigou) {
		t.Fatalf("daigou not wanted: %v", got.Sources())
	}
	if got.WantsSource(SourceDelivery) || got.WantsSource(SourceJiyun) {
		t.Errorf("expected daigou only, got %v", got.Sources())
	}

	// A filter with no named source implies a source set.
	cancelled := ParseListIntent("bekor qilingan buyurtmalar")
	if !cancelled.WantsSource(SourceDaigou) || !cancelled.WantsSource(SourceJiyun) {
		t.Errorf("cancelled should query daigou+jiyun, got %v", cancelled.Sources())
	}
	if cancelled.WantsSource(SourceDashboard) {
		t.Errorf("cancelled should not query dashboard, got %v", cancelled.Sources())
	}

	// "delayed" pulls in the sources that can actually be delayed.
	delayed := ParseListIntent("buyurtmam kelmayapti")
	if !delayed.WantsSource(SourceUnpicked) || !delayed.WantsSource(SourceDelivery) {
		t.Errorf("delayed should query delivery+unpicked, got %v", delayed.Sources())
	}

	// An unrelated question keeps the default: everything.
	if !ParseListIntent("salom").IsDefault() {
		t.Error("an unrelated question should yield the default intent")
	}
}

func TestParseListIntentIncludeCompleted(t *testing.T) {
	if !ParseListIntent("barcha buyurtmalarim").IncludeCompleted() {
		t.Error(`"barcha buyurtmalarim" should set IncludeCompleted`)
	}
	// A narrower filter wins, and clears IncludeCompleted.
	got := ParseListIntent("barcha bekor qilingan buyurtmalarim")
	if got.IncludeCompleted() {
		t.Error("a row filter must clear IncludeCompleted")
	}
	if got.RowFilter() != FilterCancelled {
		t.Errorf("RowFilter = %q, want cancelled", got.RowFilter())
	}
}

func TestMatchesFilterPerSource(t *testing.T) {
	mk := func(source string, code int) Order {
		return ReconstituteSourcedOrder(source, "X", code, "", time.Time{}, time.Time{}, nil)
	}
	cases := []struct {
		name   string
		order  Order
		filter RowFilter
		want   bool
	}{
		{"daigou cancelled 10", mk(SourceDaigou, 10), FilterCancelled, true},
		{"daigou active 2", mk(SourceDaigou, 2), FilterCancelled, false},
		{"delivery never cancelled", mk(SourceDelivery, 7), FilterCancelled, false},

		{"delivery completed 7", mk(SourceDelivery, 7), FilterCompleted, true},
		{"delivery not completed 4", mk(SourceDelivery, 4), FilterCompleted, false},
		{"jiyun completed 5", mk(SourceJiyun, 5), FilterCompleted, true},
		{"dashboard completed 3", mk(SourceDashboard, 3), FilterCompleted, true},

		// daigou 6 means "handed to logistics": it already shows as a jiyun or
		// delivery row, so it must not double up in an active list.
		{"daigou 6 excluded from active", mk(SourceDaigou, 6), FilterActive, false},
		{"daigou 2 active", mk(SourceDaigou, 2), FilterActive, true},
		{"delivery 7 not active", mk(SourceDelivery, 7), FilterActive, false},
		{"delivery 3 active", mk(SourceDelivery, 3), FilterActive, true},
		{"dashboard 1 awaiting pickup", mk(SourceDashboard, 1), FilterActive, true},
		{"dashboard 3 collected", mk(SourceDashboard, 3), FilterActive, false},

		{"delivery 4 delayed", mk(SourceDelivery, 4), FilterDelayed, true},
		{"delivery 3 not delayed", mk(SourceDelivery, 3), FilterDelayed, false},
		{"unpicked always delayed", mk(SourceUnpicked, 1), FilterDelayed, true},

		{"delivery 1 in china", mk(SourceDelivery, 1), FilterInChina, true},
		{"delivery 3 not in china", mk(SourceDelivery, 3), FilterInChina, false},
		{"daigou 5 in china", mk(SourceDaigou, 5), FilterInChina, true},
		{"daigou 6 not in china", mk(SourceDaigou, 6), FilterInChina, false},

		{"no filter keeps everything", mk(SourceDelivery, 7), FilterNone, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := MatchesFilter(c.order, c.filter); got != c.want {
				t.Errorf("MatchesFilter(%s/%d, %q) = %v, want %v",
					c.order.Source(), c.order.StatusCode(), c.filter, got, c.want)
			}
		})
	}
}

func TestApplyListIntentDropsUnwantedSourcesAndRows(t *testing.T) {
	snap := NewCustomerSnapshot(1, "", "", []Order{
		ReconstituteOrder("D-DONE", 7, "done", time.Time{}, time.Time{}, nil),
		ReconstituteOrder("D-LIVE", 3, "live", time.Time{}, time.Time{}, nil),
	}).
		WithDaigou([]Order{
			ReconstituteSourcedOrder(SourceDaigou, "DG-LIVE", 2, "", time.Time{}, time.Time{}, nil),
			ReconstituteSourcedOrder(SourceDaigou, "DG-GONE", 10, "", time.Time{}, time.Time{}, nil),
		}, 2).
		WithDashboard([]Order{
			ReconstituteSourcedOrder(SourceDashboard, "DB1", 1, "", time.Time{}, time.Time{}, nil),
		})

	// "active" wants daigou+jiyun only: delivery and dashboard must be dropped
	// wholesale, and the cancelled daigou row filtered out.
	out := ApplyListIntent(snap, ParseListIntent("aktiv buyurtmalarim"))

	if len(out.Orders()) != 0 {
		t.Errorf("delivery should be dropped for an active-scoped question, got %d", len(out.Orders()))
	}
	if len(out.DashboardOrders()) != 0 {
		t.Errorf("dashboard should be dropped, got %d", len(out.DashboardOrders()))
	}
	if len(out.DaigouOrders()) != 1 || out.DaigouOrders()[0].TrackNumber() != "DG-LIVE" {
		t.Fatalf("daigou = %+v, want only DG-LIVE", out.DaigouOrders())
	}
	// The advertised total must follow what survived, not the original count.
	if out.DaigouTotal() != 1 {
		t.Errorf("DaigouTotal = %d, want 1", out.DaigouTotal())
	}
	if out.Scope() == "" {
		t.Error("a narrowed snapshot should carry a scope description")
	}
}

func TestApplyListIntentDefaultIsNoOp(t *testing.T) {
	snap := NewCustomerSnapshot(1, "", "", []Order{
		ReconstituteOrder("D1", 7, "done", time.Time{}, time.Time{}, nil),
	}).WithDaigou([]Order{
		ReconstituteSourcedOrder(SourceDaigou, "DG1", 10, "", time.Time{}, time.Time{}, nil),
	}, 5)

	out := ApplyListIntent(snap, DefaultListIntent())

	if len(out.Orders()) != 1 || len(out.DaigouOrders()) != 1 {
		t.Errorf("default intent must keep every row, got %d delivery / %d daigou",
			len(out.Orders()), len(out.DaigouOrders()))
	}
	if out.DaigouTotal() != 5 {
		t.Errorf("DaigouTotal = %d, want the server-reported 5 to be preserved", out.DaigouTotal())
	}
	if out.Scope() != "" {
		t.Errorf("default intent should set no scope, got %q", out.Scope())
	}
}

// A filtered snapshot that came back empty must not be summarized as "you have
// no orders" - the customer may well have orders outside the asked-for scope.
func TestSummarizeDistinguishesEmptyScopeFromNoOrders(t *testing.T) {
	snap := NewCustomerSnapshot(1, "", "", []Order{
		ReconstituteOrder("D1", 3, "live", time.Time{}, time.Time{}, nil),
	})
	filtered := ApplyListIntent(snap, ParseListIntent("bekor qilingan buyurtmalarim"))

	out := Summarize(filtered, shared.LangUz, 0)
	if !strings.Contains(out, "No orders match that") {
		t.Fatalf("expected a scoped empty message, got:\n%s", out)
	}
	if strings.Contains(out, "No orders found.") {
		t.Fatalf("a filtered-empty snapshot must not claim the customer has no orders:\n%s", out)
	}

	if got := Summarize(NewCustomerSnapshot(1, "", "", nil), shared.LangUz, 0); got != "No orders found." {
		t.Errorf("a genuinely empty snapshot should say so, got %q", got)
	}
}
