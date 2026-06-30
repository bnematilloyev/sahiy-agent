package catalog

import (
	"fmt"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/channel"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// ProductSearchItem is the wire shape for Telegram product cards.
type ProductSearchItem struct {
	Title           string  `json:"title"`
	PicURL          string  `json:"pic_url"`
	DetailURL       string  `json:"detail_url"`
	PriceCNY        float64 `json:"price_cny"`
	DirectPriceCNY  float64 `json:"direct_price_cny"`
	CargoFeeCNY     float64 `json:"cargo_fee_cny"`
	Sales           int     `json:"sales"`
	NumIID          any     `json:"num_iid,omitempty"`
}

// BuildProductSearchExtra builds channel_extra for Telegram product cards.
func BuildProductSearchExtra(products []Product, keyword string, rate float64, seeAllURL string) map[string]any {
	items := make([]map[string]any, 0, len(products))
	for _, p := range products {
		if p.PicURL() == "" {
			continue
		}
		items = append(items, map[string]any{
			"title":             p.Title(),
			"pic_url":           p.PicURL(),
			"detail_url":        p.Deeplink(),
			"price_cny":         p.PriceCNY(),
			"direct_price_cny":  p.PriceCNY(),
			"cargo_fee_cny":     0.0,
			"sales":             p.Sales(),
		})
	}
	return map[string]any{
		channel.KeyProductSearchItems:         items,
		channel.KeyProductSearchCNYToUZS:      rate,
		channel.KeyProductSearchSeeAllKeyword: keyword,
		channel.KeyDisableStream:              true,
		"product_search_see_all_url":          seeAllURL,
	}
}

func FormatProductListHeader(keyword string, count int, lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return fmt.Sprintf("🔍 Результаты по запросу «%s» (%d):", keyword, count)
	case shared.LangEn.Code():
		return fmt.Sprintf("🔍 Results for «%s» (%d):", keyword, count)
	default:
		return fmt.Sprintf("🔍 «%s» bo'yicha topildi (%d ta):", keyword, count)
	}
}

// BuildCategoryKeyboard builds inline buttons for root categories.
func BuildCategoryKeyboard(cats []Category, lang shared.Language) [][]channel.InlineButton {
	const max = 12
	limit := len(cats)
	if limit > max {
		limit = max
	}
	var rows [][]channel.InlineButton
	var row []channel.InlineButton
	for i := 0; i < limit; i++ {
		c := cats[i]
		label := c.Name()
		if len([]rune(label)) > 28 {
			label = string([]rune(label)[:28]) + "…"
		}
		row = append(row, channel.InlineButton{
			Text:         label,
			CallbackData: fmt.Sprintf("ct_o_%d_0", c.ID()),
		})
		if len(row) == 2 {
			rows = append(rows, row)
			row = nil
		}
	}
	if len(row) > 0 {
		rows = append(rows, row)
	}
	return rows
}

func CategoryListHeader(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "📂 Разделы каталога Sahiy. Выберите нужный:"
	case shared.LangEn.Code():
		return "📂 Sahiy catalog sections. Pick one:"
	default:
		return "📂 Sahiy katalog bo'limlari. Keraklisini tanlang:"
	}
}

func CategoryInlineExtra(keyboard [][]channel.InlineButton) map[string]any {
	rows := make([][]map[string]string, len(keyboard))
	for i, r := range keyboard {
		rows[i] = make([]map[string]string, len(r))
		for j, btn := range r {
			m := map[string]string{"text": btn.Text}
			if btn.URL != "" {
				m["url"] = btn.URL
			} else {
				m["callback_data"] = btn.CallbackData
			}
			rows[i][j] = m
		}
	}
	return map[string]any{
		channel.KeyInlineKeyboard: rows,
		channel.KeyDisableStream:  true,
	}
}

func inlineButtonsToMaps(keyboard [][]channel.InlineButton) [][]map[string]string {
	rows := make([][]map[string]string, len(keyboard))
	for i, r := range keyboard {
		rows[i] = make([]map[string]string, len(r))
		for j, btn := range r {
			m := map[string]string{"text": btn.Text}
			if btn.URL != "" {
				m["url"] = btn.URL
			} else {
				m["callback_data"] = btn.CallbackData
			}
			rows[i][j] = m
		}
	}
	return rows
}
