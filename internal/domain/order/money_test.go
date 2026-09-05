package order

import (
	"strings"
	"testing"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

func TestNewPricingRecoversMissingFreight(t *testing.T) {
	// Sahiy left freight_fee at 0 but the total exceeds the goods cost: the
	// difference is the shipping the customer is actually being charged.
	p := NewPricing(100, 0, 130)
	if p.FreightFee() != 30 {
		t.Errorf("FreightFee = %v, want 30", p.FreightFee())
	}
	if p.Amount() != 130 || p.GoodsAmount() != 100 {
		t.Errorf("unexpected breakdown: %+v", p)
	}
}

func TestNewPricingRecoversMissingTotal(t *testing.T) {
	p := NewPricing(100, 25, 0)
	if p.Amount() != 125 {
		t.Errorf("Amount = %v, want 125", p.Amount())
	}
}

func TestNewPricingLeavesGenuineFreeShippingAlone(t *testing.T) {
	// Total equals goods: shipping really is free, and must not be invented.
	p := NewPricing(100, 0, 100)
	if p.FreightFee() != 0 {
		t.Errorf("FreightFee = %v, want 0", p.FreightFee())
	}
}

func TestNewPricingKeepsReportedFreight(t *testing.T) {
	// An explicit fee is authoritative even if it disagrees with the total.
	p := NewPricing(100, 12, 130)
	if p.FreightFee() != 12 {
		t.Errorf("FreightFee = %v, want the reported 12", p.FreightFee())
	}
}

func TestNewPricingRoundsToCents(t *testing.T) {
	p := NewPricing(10.10, 0, 30.33)
	if p.FreightFee() != 20.23 {
		t.Errorf("FreightFee = %v, want 20.23 (no float dust)", p.FreightFee())
	}
}

func TestPricingIsZero(t *testing.T) {
	if !NewPricing(0, 0, 0).IsZero() {
		t.Error("an empty breakdown should report IsZero")
	}
	if NewPricing(0, 0, 5).IsZero() {
		t.Error("a priced order should not report IsZero")
	}
}

func TestConvertToUZS(t *testing.T) {
	got, ok := ConvertToUZS(10, 1750)
	if !ok || got != 17500 {
		t.Errorf("ConvertToUZS(10, 1750) = %d, %v; want 17500, true", got, ok)
	}
	// Without a usable rate the caller must be told, not handed a zero it
	// might print as a real price.
	if _, ok := ConvertToUZS(10, 0); ok {
		t.Error("a zero rate must report ok=false")
	}
	if _, ok := ConvertToUZS(0, 1750); ok {
		t.Error("a zero amount must report ok=false")
	}
}

func TestFormatUZS(t *testing.T) {
	cases := map[int64]string{
		0:       "0",
		999:     "999",
		1000:    "1 000",
		17500:   "17 500",
		1234567: "1 234 567",
		-1000:   "-1 000",
	}
	for in, want := range cases {
		if got := FormatUZS(in); got != want {
			t.Errorf("FormatUZS(%d) = %q, want %q", in, got, want)
		}
	}
}

func TestSummarizeShowsPriceBreakdownInBothCurrencies(t *testing.T) {
	daigou := ReconstituteSourcedOrder(SourceDaigou, "DG1", 2, "buying", time.Time{}, time.Time{}, nil).
		WithPricing(NewPricing(100, 0, 130)).
		WithLocation("Guangzhou - Baiyun")
	snap := NewCustomerSnapshot(1, "", "", nil).WithDaigou([]Order{daigou}, 1)

	out := Summarize(snap, shared.LangUz, 1750)

	for _, want := range []string{
		"Goods cost: 100.00 CNY (about 175 000 UZS)",
		"Shipping inside China: 30.00 CNY (about 52 500 UZS)",
		"Order total: 130.00 CNY (about 227 500 UZS)",
		"Location: Guangzhou - Baiyun",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("Summarize missing %q:\n%s", want, out)
		}
	}
}

// Without a rate the summary must stay in CNY rather than quote a som figure
// derived from nothing.
func TestSummarizeOmitsUZSWithoutRate(t *testing.T) {
	daigou := ReconstituteSourcedOrder(SourceDaigou, "DG1", 2, "buying", time.Time{}, time.Time{}, nil).
		WithPricing(NewPricing(100, 30, 130))
	snap := NewCustomerSnapshot(1, "", "", nil).WithDaigou([]Order{daigou}, 1)

	out := Summarize(snap, shared.LangUz, 0)

	if !strings.Contains(out, "Order total: 130.00 CNY") {
		t.Errorf("expected a CNY total:\n%s", out)
	}
	if strings.Contains(out, "UZS") {
		t.Errorf("no rate was available, so no som figure may appear:\n%s", out)
	}
}

// payment_fee is already in som and must never be run through the CNY rate.
func TestSummarizePaymentFeeIsNotRateConverted(t *testing.T) {
	delivery := ReconstituteOrder("TRK1", 4, "at station", time.Time{}, time.Time{}, nil).
		WithPaymentFeeUZS(85000).
		WithLocation("Chilonzor branch")
	snap := NewCustomerSnapshot(1, "", "", []Order{delivery})

	out := Summarize(snap, shared.LangUz, 1750)

	if !strings.Contains(out, "Amount due on collection: 85 000 UZS") {
		t.Errorf("payment fee should appear verbatim in som:\n%s", out)
	}
	if !strings.Contains(out, "Location: Chilonzor branch") {
		t.Errorf("branch missing:\n%s", out)
	}
}

func TestSummarizeOmitsMoneyLinesWhenAbsent(t *testing.T) {
	plain := ReconstituteOrder("TRK1", 3, "in transit", time.Time{}, time.Time{}, nil)
	out := Summarize(NewCustomerSnapshot(1, "", "", []Order{plain}), shared.LangUz, 1750)

	for _, unwanted := range []string{"Order total", "Amount due", "Location:"} {
		if strings.Contains(out, unwanted) {
			t.Errorf("an order with no money/location data should not print %q:\n%s", unwanted, out)
		}
	}
}
