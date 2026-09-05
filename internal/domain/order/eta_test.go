package order

import (
	"testing"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

func TestResolveLogisticsStatus(t *testing.T) {
	cases := []struct {
		source     string
		statusCode int
		want       LogisticsStatus
		wantOK     bool
	}{
		{SourceDaigou, 6, 4, true},
		{SourceDaigou, 99, 0, false},
		{SourceDelivery, 7, StageDelivered, true},
		{SourceDelivery, 1, 3, true},
		{SourceJiyun, 5, StageDelivered, true},
		{SourceDashboard, 1, 0, false}, // no mapping ported yet (no data source)
	}
	for _, c := range cases {
		got, ok := ResolveLogisticsStatus(c.source, c.statusCode)
		if ok != c.wantOK || got != c.want {
			t.Errorf("ResolveLogisticsStatus(%q, %d) = (%d, %v), want (%d, %v)",
				c.source, c.statusCode, got, ok, c.want, c.wantOK)
		}
	}
}

func TestEstimateRemainingDays(t *testing.T) {
	cases := []struct {
		status LogisticsStatus
		want   int
	}{
		{12, 0},                            // delivered
		{13, 0},                            // past delivered, clamp to 0
		{11, 3},                            // last stage only
		{4, 4 + 5 + 1 + 1 + 1 + 2 + 1 + 3}, // stages 4..11 summed
		{0, 1 + 3 + 1 + 4 + 5 + 1 + 1 + 1 + 2 + 1 + 3}, // below 1, clamps to stage 1
	}
	for _, c := range cases {
		if got := EstimateRemainingDays(c.status); got != c.want {
			t.Errorf("EstimateRemainingDays(%d) = %d, want %d", c.status, got, c.want)
		}
	}
}

func TestLogisticsStatusLabel(t *testing.T) {
	if got := LogisticsStatusLabel(4, shared.LangRu); got != "В пути в Кыргызстан" {
		t.Errorf("LogisticsStatusLabel(4, ru) = %q", got)
	}
	if got := LogisticsStatusLabel(4, shared.LangEn); got != "On the way to Kyrgyzstan" {
		t.Errorf("LogisticsStatusLabel(4, en) = %q", got)
	}
	if got := LogisticsStatusLabel(99, shared.LangEn); got != "" {
		t.Errorf("LogisticsStatusLabel(99, en) = %q, want empty", got)
	}
}

func TestEstimateETA(t *testing.T) {
	daigouOrder := ReconstituteSourcedOrder(SourceDaigou, "DG1", 6, "shipped", time.Time{}, time.Time{}, nil)
	eta, ok := EstimateETA(daigouOrder, shared.LangEn)
	if !ok {
		t.Fatal("expected ok=true for known daigou status")
	}
	if eta.Delivered {
		t.Fatal("status 6 (stage 4) should not be delivered")
	}
	if eta.RemainingDays != 18 {
		t.Errorf("RemainingDays = %d, want 18", eta.RemainingDays)
	}
	if eta.StatusLabel != "On the way to Kyrgyzstan" {
		t.Errorf("StatusLabel = %q", eta.StatusLabel)
	}

	deliveredOrder := ReconstituteOrder("TRK1", 7, "delivered", time.Time{}, time.Time{}, nil)
	eta, ok = EstimateETA(deliveredOrder, shared.LangEn)
	if !ok || !eta.Delivered {
		t.Fatalf("expected delivered=true, got %+v ok=%v", eta, ok)
	}

	unknownOrder := ReconstituteSourcedOrder(SourceDashboard, "X", 1, "?", time.Time{}, time.Time{}, nil)
	if _, ok := EstimateETA(unknownOrder, shared.LangEn); ok {
		t.Fatal("expected ok=false for a source with no logistics mapping")
	}
}
