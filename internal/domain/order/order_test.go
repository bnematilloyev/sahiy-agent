package order

import (
	"strings"
	"testing"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

func TestSummarizeIncludesETA(t *testing.T) {
	daigouOrder := ReconstituteSourcedOrder(SourceDaigou, "DG1", 6, "shipped", time.Time{}, time.Time{}, nil)
	snapshot := NewCustomerSnapshot(1, "", "", nil).WithDaigou([]Order{daigouOrder}, 1)

	out := Summarize(snapshot, shared.LangUz, 0)

	if !strings.Contains(out, "ETA: ~18 days (stage: On the way to Kyrgyzstan)") {
		t.Fatalf("Summarize output missing computed ETA line:\n%s", out)
	}
}

func TestSummarizeDeliveredOrderShowsDeliveredETA(t *testing.T) {
	delivered := ReconstituteOrder("TRK1", 7, "delivered", time.Time{}, time.Time{}, nil)
	snapshot := NewCustomerSnapshot(1, "", "", []Order{delivered})

	out := Summarize(snapshot, shared.LangUz, 0)

	if !strings.Contains(out, "ETA: delivered") {
		t.Fatalf("Summarize output missing delivered ETA line:\n%s", out)
	}
}
