package sahiy

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/config"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/order"
)

func discardLog() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

// newTestCustomerAPI wires a CustomerAPI against a test server. daigouList is
// left nil so tests exercise the delivery/jiyun/dashboard/unpicked paths only.
func newTestCustomerAPI(t *testing.T, baseURL string) *CustomerAPI {
	t.Helper()
	cfg := config.Sahiy{
		BaseURL:           baseURL,
		ServiceUserPhone:  "x",
		ServiceUserPass:   "y",
		ServiceUserDevice: "d",
		Timeout:           5 * time.Second,
	}
	log := discardLog()
	auth := newServiceUserAuth(cfg, &http.Client{Timeout: cfg.Timeout}, log)
	return &CustomerAPI{client: newClient(cfg.BaseURL, auth, cfg.Timeout, log), log: log}
}

// TestBuildSnapshotAggregatesAllSources verifies buildSnapshot fetches
// delivery, jiyun, dashboard and unpicked concurrently and merges all four
// into the returned snapshot. Run with -race to catch any data race in the
// goroutines that populate it.
func TestBuildSnapshotAggregatesAllSources(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v2/service/user/login/", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": "tok", "expires_in": 3600})
	})
	mux.HandleFunc("/api/v2/admin/delivery/orders/user/42", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{
			{"track_number": "TRK1", "status": 1},
		}})
	})
	mux.HandleFunc("/api/custom/orders", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{
			{"track_number": "JY1", "status": 3},
		}})
	})
	mux.HandleFunc("/api/client/dashboard/show/42", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{
			{"track_number": "DB1", "status": 1},
		}})
	})
	mux.HandleFunc("/api/v2/admin/delivery/orders/filter", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{
			{"track_number": "UP1", "status": 4},
		}})
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	api := newTestCustomerAPI(t, srv.URL)

	snap, err := api.buildSnapshot(context.Background(), 42, "", "")
	if err != nil {
		t.Fatalf("buildSnapshot: %v", err)
	}

	if got := len(snap.Orders()); got != 1 || snap.Orders()[0].TrackNumber() != "TRK1" {
		t.Errorf("Orders = %+v", snap.Orders())
	}
	if got := len(snap.JiyunOrders()); got != 1 || snap.JiyunOrders()[0].TrackNumber() != "JY1" {
		t.Errorf("JiyunOrders = %+v", snap.JiyunOrders())
	}
	if got := len(snap.DashboardOrders()); got != 1 || snap.DashboardOrders()[0].TrackNumber() != "DB1" {
		t.Errorf("DashboardOrders = %+v", snap.DashboardOrders())
	}
	if got := len(snap.UnpickedOrders()); got != 1 || snap.UnpickedOrders()[0].TrackNumber() != "UP1" {
		t.Errorf("UnpickedOrders = %+v", snap.UnpickedOrders())
	}
	if snap.UnpickedOrders()[0].Source() != "unpicked" {
		t.Errorf("unpicked order source = %q, want %q", snap.UnpickedOrders()[0].Source(), "unpicked")
	}
}

// TestLookupWithListIntentSkipsUnwantedSources is the point of the list intent:
// sources the question did not ask about must not be requested at all, so the
// answer costs fewer HTTP round-trips rather than being filtered after the fact.
func TestLookupWithListIntentSkipsUnwantedSources(t *testing.T) {
	hit := map[string]int{}
	var mu sync.Mutex
	record := func(name string) {
		mu.Lock()
		hit[name]++
		mu.Unlock()
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/api/v2/service/user/login/", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": "tok", "expires_in": 3600})
	})
	mux.HandleFunc("/api/v2/admin/delivery/orders/user/42", func(w http.ResponseWriter, r *http.Request) {
		record("delivery")
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{
			{"track_number": "TRK1", "status": 1},
		}})
	})
	mux.HandleFunc("/api/custom/orders", func(w http.ResponseWriter, r *http.Request) {
		record("jiyun")
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	mux.HandleFunc("/api/client/dashboard/show/42", func(w http.ResponseWriter, r *http.Request) {
		record("dashboard")
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	mux.HandleFunc("/api/v2/admin/delivery/orders/filter", func(w http.ResponseWriter, r *http.Request) {
		record("unpicked")
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	api := newTestCustomerAPI(t, srv.URL)

	// "aktiv buyurtmalarim" resolves to daigou+jiyun, so delivery, dashboard
	// and unpicked must never be requested.
	if _, err := api.Lookup(context.Background(), order.LookupRequest{
		Query: "aktiv buyurtmalarim", VerifiedUserID: 42,
	}); err != nil {
		t.Fatalf("Lookup: %v", err)
	}

	mu.Lock()
	defer mu.Unlock()
	if hit["jiyun"] != 1 {
		t.Errorf("jiyun should have been fetched once, got %d", hit["jiyun"])
	}
	for _, skipped := range []string{"delivery", "dashboard", "unpicked"} {
		if hit[skipped] != 0 {
			t.Errorf("%s should not be fetched for an active-scoped question, got %d calls",
				skipped, hit[skipped])
		}
	}
}

// A track lookup must still search every source: the customer named one
// parcel, so it has to be found wherever it lives.
func TestLookupByTrackStillQueriesEverySource(t *testing.T) {
	hit := map[string]int{}
	var mu sync.Mutex
	record := func(name string) {
		mu.Lock()
		hit[name]++
		mu.Unlock()
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/api/v2/service/user/login/", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": "tok", "expires_in": 3600})
	})
	mux.HandleFunc("/api/v2/admin/delivery/orders/user/42", func(w http.ResponseWriter, r *http.Request) {
		record("delivery")
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	mux.HandleFunc("/api/custom/orders", func(w http.ResponseWriter, r *http.Request) {
		record("jiyun")
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	mux.HandleFunc("/api/client/dashboard/show/42", func(w http.ResponseWriter, r *http.Request) {
		record("dashboard")
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	mux.HandleFunc("/api/v2/admin/delivery/orders/filter", func(w http.ResponseWriter, r *http.Request) {
		record("unpicked")
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	api := newTestCustomerAPI(t, srv.URL)

	if _, err := api.Lookup(context.Background(), order.LookupRequest{
		Query: "TRACK123456789", VerifiedUserID: 42,
	}); err != nil {
		t.Fatalf("Lookup: %v", err)
	}

	mu.Lock()
	defer mu.Unlock()
	for _, source := range []string{"delivery", "jiyun", "dashboard", "unpicked"} {
		if hit[source] == 0 {
			t.Errorf("%s should still be queried for a track lookup", source)
		}
	}
}

func TestCollectIdentifiersReadsNestedParcelNumbers(t *testing.T) {
	row := map[string]json.RawMessage{
		"order_sn":          json.RawMessage(`"DG1"`),
		"express_num":       json.RawMessage(`"EX-1"`),
		"purchase_packages": json.RawMessage(`[{"express_num":"PKG-1"},{"express_num":"PKG-2"}]`),
		"expresses":         json.RawMessage(`[{"pivot":{"express_num":"PIV-1"},"express":{"express_num":"INNER-1"}}]`),
		"express":           json.RawMessage(`{"express_num":"TOP-1"}`),
		// Wrongly-typed fields must be skipped, not panic.
		"logistics_sn": json.RawMessage(`12345`),
	}

	got := map[string]bool{}
	for _, id := range collectIdentifiers(row) {
		got[id] = true
	}
	for _, want := range []string{"DG1", "EX-1", "PKG-1", "PKG-2", "PIV-1", "INNER-1", "TOP-1"} {
		if !got[want] {
			t.Errorf("collectIdentifiers missing %q; got %v", want, got)
		}
	}
}

// End-to-end: the same parcel returned by both the delivery list and the
// "not delivered" filter must reach the domain as one order, not two.
func TestBuildSnapshotDeduplicatesDeliveryAndUnpicked(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v2/service/user/login/", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": "tok", "expires_in": 3600})
	})
	mux.HandleFunc("/api/v2/admin/delivery/orders/user/42", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{
			{"track_number": "SF-100 200", "status": 4},
		}})
	})
	mux.HandleFunc("/api/v2/admin/delivery/orders/filter", func(w http.ResponseWriter, r *http.Request) {
		// The same parcel, spelled without separators.
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{
			{"track_number": "SF100200", "status": 4},
		}})
	})
	mux.HandleFunc("/api/custom/orders", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	mux.HandleFunc("/api/client/dashboard/show/42", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	api := newTestCustomerAPI(t, srv.URL)
	snap, err := api.buildSnapshot(context.Background(), 42, "", "")
	if err != nil {
		t.Fatalf("buildSnapshot: %v", err)
	}

	total := len(snap.Orders()) + len(snap.UnpickedOrders())
	if total != 1 {
		t.Fatalf("one parcel reported by two endpoints should appear once, got %d "+
			"(delivery=%+v unpicked=%+v)", total, snap.Orders(), snap.UnpickedOrders())
	}
}

func TestBranchFromRowReadsNestedLocation(t *testing.T) {
	cases := []struct {
		name string
		row  string
		want string
	}{
		{"flat branch_name", `{"branch_name":"Chilonzor"}`, "Chilonzor"},
		{"location_number wins", `{"location_number":"P-12","branch_name":"Chilonzor"}`, "P-12"},
		{"nested location", `{"location":{"branch_name":"Yunusobod"}}`, "Yunusobod"},
		{"nested location.name", `{"location":{"name":"Sergeli"}}`, "Sergeli"},
		{"nested location.branch", `{"location":{"branch":{"name":"Olmazor"}}}`, "Olmazor"},
		{"absent", `{}`, ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			var row map[string]json.RawMessage
			if err := json.Unmarshal([]byte(c.row), &row); err != nil {
				t.Fatalf("bad fixture: %v", err)
			}
			if got := branchFromRow(row); got != c.want {
				t.Errorf("branchFromRow = %q, want %q", got, c.want)
			}
		})
	}
}

func TestPaymentFeePrefersActual(t *testing.T) {
	var row map[string]json.RawMessage
	if err := json.Unmarshal([]byte(`{"payment_fee":50000,"actual_payment_fee":42000}`), &row); err != nil {
		t.Fatalf("bad fixture: %v", err)
	}
	if got := paymentFeeFromRow(row); got != 42000 {
		t.Errorf("paymentFeeFromRow = %v, want the settled 42000", got)
	}
}

func TestMapDaigouRowCarriesPricingAndLocation(t *testing.T) {
	var row map[string]json.RawMessage
	fixture := `{"order_sn":"DG1","status":2,"goods_amount":100,"amount":130,
	             "area_name":"Guangzhou","sub_area_name":"Baiyun"}`
	if err := json.Unmarshal([]byte(fixture), &row); err != nil {
		t.Fatalf("bad fixture: %v", err)
	}

	o := mapDaigouRow(row)

	if o.Pricing().FreightFee() != 30 {
		t.Errorf("freight should be recovered as 130-100, got %v", o.Pricing().FreightFee())
	}
	if o.Location() != "Guangzhou - Baiyun" {
		t.Errorf("Location = %q", o.Location())
	}
}

// SKU enrichment replaces an order's items. It must not take the identifiers,
// pricing or location with it - rebuilding the order used to drop all three.
func TestSKUEnrichmentKeepsIdentifiersAndMoney(t *testing.T) {
	var row map[string]json.RawMessage
	fixture := `{"track_number":"TRK-1","status":4,"express_num":"EX-9",
	             "payment_fee":85000,"branch_name":"Chilonzor"}`
	if err := json.Unmarshal([]byte(fixture), &row); err != nil {
		t.Fatalf("bad fixture: %v", err)
	}
	original := mapRowToOrder(row)

	enriched := original.WithItems([]order.OrderItem{
		order.NewOrderItem("shoes", "SKU1", 1, 10, "CNY", "http://img"),
	})

	if len(enriched.Items()) != 1 {
		t.Fatalf("items were not replaced: %+v", enriched.Items())
	}
	if enriched.PaymentFeeUZS() != 85000 {
		t.Errorf("payment fee lost by enrichment: %v", enriched.PaymentFeeUZS())
	}
	if enriched.Location() != "Chilonzor" {
		t.Errorf("location lost by enrichment: %q", enriched.Location())
	}
	if len(enriched.TrackKeys()) != len(original.TrackKeys()) {
		t.Errorf("identifiers lost by enrichment: %v vs %v",
			enriched.TrackKeys(), original.TrackKeys())
	}
}

// TestBuildSnapshotToleratesPartialFailure verifies a failing secondary source
// (jiyun here) does not fail the whole lookup - the other sources still come
// back, matching the "best effort per source" behavior of the Python original.
func TestBuildSnapshotToleratesPartialFailure(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v2/service/user/login/", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": "tok", "expires_in": 3600})
	})
	mux.HandleFunc("/api/v2/admin/delivery/orders/user/42", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{
			{"track_number": "TRK1", "status": 1},
		}})
	})
	mux.HandleFunc("/api/custom/orders", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	})
	mux.HandleFunc("/api/client/dashboard/show/42", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	mux.HandleFunc("/api/v2/admin/delivery/orders/filter", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	api := newTestCustomerAPI(t, srv.URL)

	snap, err := api.buildSnapshot(context.Background(), 42, "", "")
	if err != nil {
		t.Fatalf("buildSnapshot: %v", err)
	}
	if len(snap.Orders()) != 1 {
		t.Errorf("expected delivery order to still come back, got %+v", snap.Orders())
	}
	if len(snap.JiyunOrders()) != 0 {
		t.Errorf("expected no jiyun orders after a 500, got %+v", snap.JiyunOrders())
	}
}

// newSKUTestAPI wires a CustomerAPI whose admin client points at the same test
// server, so SKU enrichment calls can be counted.
func newSKUTestAPI(t *testing.T, baseURL string, maxOrders, concurrency int) *CustomerAPI {
	t.Helper()
	api := newTestCustomerAPI(t, baseURL)
	api.skuEnabled = true
	api.skuEnrichMaxOrders = maxOrders
	api.skuEnrichConcurrency = concurrency
	api.daigou = NewDaigouAdmin(NewAdminClient(config.Sahiy{
		BaseURL:          baseURL,
		AdminAccessToken: "admin-tok",
		Timeout:          5 * time.Second,
	}, NewAdminAuth(config.Sahiy{
		BaseURL:          baseURL,
		AdminAccessToken: "admin-tok",
		Timeout:          5 * time.Second,
	}), discardLog()), discardLog())
	return api
}

// deliveryRowsJSON builds n delivery rows, newest first.
func deliveryRowsJSON(n int) map[string]any {
	rows := make([]map[string]any, 0, n)
	for i := 0; i < n; i++ {
		rows = append(rows, map[string]any{
			"track_number": fmt.Sprintf("TRK%03d", i),
			"order_sn":     fmt.Sprintf("DG%03d", i),
			"status":       3,
			"created_at":   fmt.Sprintf("2026-01-%02dT10:00:00Z", 28-i),
		})
	}
	return map[string]any{"data": rows}
}

// A track lookup used to enrich every order the customer had and then throw
// all but one away. It must now pay for the one it keeps.
func TestTrackLookupEnrichesOnlyTheMatchedOrder(t *testing.T) {
	var enrichCalls int32
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v2/service/user/login/", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": "tok", "expires_in": 3600})
	})
	mux.HandleFunc("/api/v2/admin/delivery/orders/user/42", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(deliveryRowsJSON(20))
	})
	mux.HandleFunc("/api/admin/daigou-orders/", func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&enrichCalls, 1)
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	api := newSKUTestAPI(t, srv.URL, 10, 4)
	snap, err := api.buildSnapshot(context.Background(), 42, "TRK005", "")
	if err != nil {
		t.Fatalf("buildSnapshot: %v", err)
	}
	if len(snap.Orders()) != 1 || snap.Orders()[0].TrackNumber() != "TRK005" {
		t.Fatalf("expected only TRK005, got %+v", snap.Orders())
	}
	// Exactly one: zero would mean the test never exercised enrichment at all,
	// and the assertion below would pass for the wrong reason.
	if got := atomic.LoadInt32(&enrichCalls); got != 1 {
		t.Errorf("enrichment ran %d times for a single-order lookup, want exactly 1", got)
	}
}

// A list question must enrich at most the configured number of orders, and
// still return every order it fetched.
func TestListLookupEnrichesOnlyTheMostRecentOrders(t *testing.T) {
	var enrichCalls int32
	var mu sync.Mutex
	seen := map[string]bool{}

	mux := http.NewServeMux()
	mux.HandleFunc("/api/v2/service/user/login/", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": "tok", "expires_in": 3600})
	})
	mux.HandleFunc("/api/v2/admin/delivery/orders/user/42", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(deliveryRowsJSON(20))
	})
	mux.HandleFunc("/api/admin/daigou-orders/", func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&enrichCalls, 1)
		mu.Lock()
		seen[r.URL.Query().Get("order_sn")] = true
		mu.Unlock()
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	api := newSKUTestAPI(t, srv.URL, 5, 4)
	snap, err := api.buildSnapshot(context.Background(), 42, "", "")
	if err != nil {
		t.Fatalf("buildSnapshot: %v", err)
	}

	if len(snap.Orders()) != 20 {
		t.Errorf("all 20 orders must still be returned, got %d", len(snap.Orders()))
	}
	got := atomic.LoadInt32(&enrichCalls)
	if got == 0 {
		t.Fatal("enrichment never ran; the test is not exercising the capped path")
	}
	if got > 5 {
		t.Errorf("enrichment ran %d times, want at most the cap of 5", got)
	}
	// The cap must pick the newest rows: DG000 has the latest created_at.
	mu.Lock()
	defer mu.Unlock()
	if !seen["DG000"] {
		t.Errorf("the newest order was not among the enriched ones: %v", seen)
	}
	if seen["DG019"] {
		t.Errorf("the oldest order was enriched despite the cap: %v", seen)
	}
}

func TestMostRecentIndexes(t *testing.T) {
	mk := func(day int) deliveryRow {
		var created time.Time
		if day > 0 {
			created = time.Date(2026, 1, day, 0, 0, 0, 0, time.UTC)
		}
		return deliveryRow{order: order.ReconstituteOrder("T", 1, "", created, time.Time{}, nil)}
	}
	rows := []deliveryRow{mk(1), mk(9), mk(0), mk(5)} // index 2 has no date

	got := mostRecentIndexes(rows, 2)

	// Newest two are index 1 (Jan 9) and index 3 (Jan 5), returned in index order.
	if len(got) != 2 || got[0] != 1 || got[1] != 3 {
		t.Fatalf("mostRecentIndexes = %v, want [1 3]", got)
	}
	// A non-positive cap means everything, in original order.
	if all := mostRecentIndexes(rows, 0); len(all) != 4 || all[0] != 0 || all[3] != 3 {
		t.Errorf("uncapped = %v, want [0 1 2 3]", all)
	}
	// Undated rows must sort last, so they are the first to be dropped.
	if one := mostRecentIndexes(rows, 3); len(one) != 3 || one[2] == 2 && one[0] == 2 {
		t.Errorf("unexpected selection %v", one)
	}
}
