package order

import (
	"fmt"
	"math"
	"strings"
)

// Pricing is an order's cost breakdown, in CNY, as Sahiy reports it for a
// China purchase.
//
// The fields are not independent, and Sahiy does not always populate all
// three, so NewPricing reconciles them rather than storing whatever arrived.
type Pricing struct {
	goodsAmount float64
	freightFee  float64
	amount      float64
}

// NewPricing derives a complete breakdown from whatever the API supplied.
//
// Two gaps get filled. A missing freight fee is recovered as total minus
// goods, which is what it is by definition - without this the customer is told
// shipping is free when it simply was not itemized. A missing total is the sum
// of its parts. Neither can be left to the model: it would be guessing at
// arithmetic on money.
func NewPricing(goodsAmount, freightFee, amount float64) Pricing {
	if freightFee <= 0 && amount > goodsAmount && goodsAmount > 0 {
		freightFee = round2(amount - goodsAmount)
	}
	if amount <= 0 {
		amount = round2(goodsAmount + freightFee)
	}
	return Pricing{goodsAmount: goodsAmount, freightFee: freightFee, amount: amount}
}

func (p Pricing) GoodsAmount() float64 { return p.goodsAmount }
func (p Pricing) FreightFee() float64  { return p.freightFee }
func (p Pricing) Amount() float64      { return p.amount }

// IsZero reports that there is no priced total to show.
func (p Pricing) IsZero() bool { return p.amount <= 0 }

func round2(v float64) float64 { return math.Round(v*100) / 100 }

// ConvertToUZS converts a CNY amount at the given rate. ok is false when no
// usable rate was available, in which case the amount must be shown in CNY
// rather than as a made-up number.
func ConvertToUZS(cny, rate float64) (int64, bool) {
	if rate <= 0 || cny <= 0 {
		return 0, false
	}
	return int64(math.Round(cny * rate)), true
}

// FormatUZS renders a som amount with space-grouped thousands ("1 234 567"),
// the convention Sahiy uses in its own apps.
func FormatUZS(amount int64) string {
	digits := fmt.Sprintf("%d", amount)
	neg := strings.HasPrefix(digits, "-")
	digits = strings.TrimPrefix(digits, "-")

	var b strings.Builder
	for i, r := range digits {
		if i > 0 && (len(digits)-i)%3 == 0 {
			b.WriteByte(' ')
		}
		b.WriteRune(r)
	}
	if neg {
		return "-" + b.String()
	}
	return b.String()
}

// formatMoneyCNY renders a CNY amount, adding the som equivalent when a rate
// is available. Both are given because the customer may have been quoted
// either, and the model cannot compute the conversion itself.
func formatMoneyCNY(cny, rate float64) string {
	out := fmt.Sprintf("%.2f CNY", cny)
	if uzs, ok := ConvertToUZS(cny, rate); ok {
		out += fmt.Sprintf(" (about %s UZS)", FormatUZS(uzs))
	}
	return out
}
