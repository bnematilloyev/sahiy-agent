package sahiy

import (
	"encoding/json"
	"testing"
)

func TestIntentStatusCodes(t *testing.T) {
	cases := []struct {
		filter    string
		wantCodes []int
		wantUse   bool
	}{
		{"", []int{0, 1, 2, 3, 4, 5}, true},
		{"active", []int{1, 2, 3, 4, 5}, true},
		{"cancelled", []int{10, 11}, true},
		{"completed", []int{6}, true},
		{"in_china", []int{0, 1, 2, 3, 4, 5}, true},
		{"nonsense", nil, false},
	}
	for _, c := range cases {
		codes, use := intentStatusCodes(c.filter)
		if use != c.wantUse {
			t.Errorf("intentStatusCodes(%q) useFilter=%v want %v", c.filter, use, c.wantUse)
		}
		if len(codes) != len(c.wantCodes) {
			t.Errorf("intentStatusCodes(%q) = %v want %v", c.filter, codes, c.wantCodes)
			continue
		}
		for i := range codes {
			if codes[i] != c.wantCodes[i] {
				t.Errorf("intentStatusCodes(%q)[%d] = %d want %d", c.filter, i, codes[i], c.wantCodes[i])
			}
		}
	}
}

func TestExtractDaigouPage(t *testing.T) {
	body := `{
		"count": 42,
		"data": {
			"current_page": 2,
			"last_page": 5,
			"total": 42,
			"data": [
				{"order_sn": "DG12345", "status": 2},
				{"order_sn": "DG67890", "status": 5}
			]
		}
	}`
	pg := extractDaigouPage(json.RawMessage(body))
	if len(pg.items) != 2 {
		t.Fatalf("expected 2 items, got %d", len(pg.items))
	}
	if pg.current != 2 || pg.last != 5 {
		t.Errorf("pagination = current %d last %d, want 2/5", pg.current, pg.last)
	}
	if total := daigouTotal(json.RawMessage(body), len(pg.items)); total != 42 {
		t.Errorf("daigouTotal = %d, want 42", total)
	}
	if sn := rawStrFromMap(pg.items[0], "order_sn"); sn != "DG12345" {
		t.Errorf("first order_sn = %q, want DG12345", sn)
	}
}

func TestExtractCustomPageFlatList(t *testing.T) {
	body := `{"total": 3, "data": [{"order_sn": "DG1"}, {"order_sn": "DG2"}]}`
	pg := extractCustomPage(json.RawMessage(body))
	if len(pg.items) != 2 {
		t.Fatalf("expected 2 items, got %d", len(pg.items))
	}
	if total := customDaigouTotal(json.RawMessage(body), len(pg.items)); total != 3 {
		t.Errorf("customDaigouTotal = %d, want 3", total)
	}
}

func TestExtractDaigouPageEmpty(t *testing.T) {
	pg := extractDaigouPage(json.RawMessage(`{}`))
	if len(pg.items) != 0 || pg.current != 1 || pg.last != 1 {
		t.Errorf("empty body should yield no items and 1/1 pagination, got %+v", pg)
	}
}
