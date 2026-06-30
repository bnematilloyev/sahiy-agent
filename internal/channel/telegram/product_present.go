package telegram

import (
	"fmt"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

func formatProductCaption(item map[string]any, lang shared.Language, rate float64, index int) string {
	title, _ := item["title"].(string)
	priceCNY, _ := item["price_cny"].(float64)
	sales, _ := item["sales"].(float64)
	var b strings.Builder
	b.WriteString(fmt.Sprintf("%d. %s\n", index, title))
	if priceCNY > 0 {
		uzs := priceCNY * rate
		switch lang.Code() {
		case shared.LangRu.Code():
			fmt.Fprintf(&b, "💰 Цена: %.0f so'm (%.0f CNY)\n", uzs, priceCNY)
		case shared.LangEn.Code():
			fmt.Fprintf(&b, "💰 Price: %.0f so'm (%.0f CNY)\n", uzs, priceCNY)
		default:
			fmt.Fprintf(&b, "💰 Narx: %.0f so'm (%.0f CNY)\n", uzs, priceCNY)
		}
	}
	if sales > 0 {
		switch lang.Code() {
		case shared.LangRu.Code():
			fmt.Fprintf(&b, "📦 Продажи: %.0f", sales)
		case shared.LangEn.Code():
			fmt.Fprintf(&b, "📦 Sales: %.0f", sales)
		default:
			fmt.Fprintf(&b, "📦 Sotuvlar: %.0f", sales)
		}
	}
	return strings.TrimSpace(b.String())
}

func buyLabel(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "🛒 Купить"
	case shared.LangEn.Code():
		return "🛒 Buy"
	default:
		return "🛒 Sotib olish"
	}
}
