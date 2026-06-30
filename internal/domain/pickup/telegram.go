package pickup

import (
	"fmt"
	"sort"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/channel"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

const callbackPrefix = "pp"

// BuildRegionKeyboard builds inline region/type buttons for Telegram.
func BuildRegionKeyboard(points []Point) [][]channel.InlineButton {
	regions := map[int64]string{}
	for _, p := range points {
		if p.RegionID() != 0 && p.RegionName() != "" {
			regions[p.RegionID()] = p.RegionName()
		}
	}
	type pair struct {
		id   int64
		name string
	}
	sorted := make([]pair, 0, len(regions))
	for id, name := range regions {
		sorted = append(sorted, pair{id, name})
	}
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].name < sorted[j].name })

	var rows [][]channel.InlineButton
	var row []channel.InlineButton
	for i, p := range sorted {
		if i >= 12 {
			break
		}
		label := p.name
		if len([]rune(label)) > 32 {
			label = string([]rune(label)[:32])
		}
		row = append(row, channel.InlineButton{
			Text:         label,
			CallbackData: fmt.Sprintf("%s_r_%d", callbackPrefix, p.id),
		})
		if len(row) == 2 {
			rows = append(rows, row)
			row = nil
		}
	}
	if len(row) > 0 {
		rows = append(rows, row)
	}
	rows = append(rows, []channel.InlineButton{
		{Text: "🏪 Filial", CallbackData: callbackPrefix + "_t_1"},
		{Text: "📮 Postomat", CallbackData: callbackPrefix + "_t_2"},
	})
	return rows
}

// FilterByRegionID returns points in the given region.
func FilterByRegionID(regionID int64, points []Point) []Point {
	var out []Point
	for _, p := range points {
		if p.RegionID() == regionID {
			out = append(out, p)
		}
	}
	return out
}

// FilterByType returns points matching type code (1=filial, 2=postomat).
func FilterByType(typeCode int, points []Point) []Point {
	var out []Point
	for _, p := range points {
		if p.TypeCode() == typeCode {
			out = append(out, p)
		}
	}
	return out
}

// ParseCallback parses pp_r_{id} or pp_t_{code} callbacks.
func ParseCallback(data string) (kind string, value int, ok bool) {
	if len(data) < 5 || data[:3] != callbackPrefix+"_" {
		return "", 0, false
	}
	parts := splitCallback(data)
	if len(parts) < 3 {
		return "", 0, false
	}
	switch parts[1] {
	case "r", "t":
		var v int
		if _, err := fmt.Sscanf(parts[2], "%d", &v); err != nil {
			return "", 0, false
		}
		return parts[1], v, true
	default:
		return "", 0, false
	}
}

func splitCallback(data string) []string {
	var parts []string
	start := 0
	for i := 0; i < len(data); i++ {
		if data[i] == '_' {
			parts = append(parts, data[start:i])
			start = i + 1
		}
	}
	parts = append(parts, data[start:])
	return parts
}

func PickupInlineExtra(keyboard [][]channel.InlineButton, count int) map[string]any {
	rows := make([][]map[string]string, len(keyboard))
	for i, r := range keyboard {
		rows[i] = make([]map[string]string, len(r))
		for j, btn := range r {
			rows[i][j] = map[string]string{"text": btn.Text, "callback_data": btn.CallbackData}
		}
	}
	return map[string]any{
		channel.KeyInlineKeyboard:    rows,
		channel.KeyPickupPointsCount: count,
		channel.KeyDisableStream:     true,
	}
}

func OverviewHeader(lang shared.Language, count int) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return fmt.Sprintf("📍 Пункты выдачи (%d). Выберите регион:", count)
	case shared.LangEn.Code():
		return fmt.Sprintf("📍 Pickup points (%d). Choose a region:", count)
	default:
		return fmt.Sprintf("📍 Topshirish punktlari (%d ta). Viloyatni tanlang:", count)
	}
}
