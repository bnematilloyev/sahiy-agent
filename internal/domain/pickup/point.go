// Package pickup holds pure domain types and presenters for pickup points.
package pickup

import (
	"fmt"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// Point is a pickup location (filial or postomat).
type Point struct {
	id         int64
	regionID   int64
	name       string
	address    string
	phone      string
	typeLabel  string
	typeCode   int
	regionName string
	cityName   string
}

// NewPoint constructs a Point.
func NewPoint(id, regionID int64, name, address, phone, typeLabel string, typeCode int, regionName, cityName string) Point {
	return Point{
		id: id, regionID: regionID, name: name, address: address, phone: phone,
		typeLabel: typeLabel, typeCode: typeCode, regionName: regionName, cityName: cityName,
	}
}

func (p Point) ID() int64         { return p.id }
func (p Point) RegionID() int64   { return p.regionID }
func (p Point) Name() string      { return p.name }
func (p Point) Address() string    { return p.address }
func (p Point) Phone() string      { return p.phone }
func (p Point) TypeLabel() string  { return p.typeLabel }
func (p Point) TypeCode() int      { return p.typeCode }
func (p Point) RegionName() string { return p.regionName }
func (p Point) CityName() string   { return p.cityName }

// FilterByLocationQuery returns points whose region/city/address match query tokens.
func FilterByLocationQuery(query string, points []Point) []Point {
	tokens := strings.Fields(strings.ToLower(query))
	if len(tokens) == 0 {
		return nil
	}
	var out []Point
	for _, p := range points {
		hay := strings.ToLower(p.regionName + " " + p.cityName + " " + p.address + " " + p.name)
		matched := 0
		for _, t := range tokens {
			if len(t) < 3 {
				continue
			}
			if strings.Contains(hay, t) {
				matched++
			}
		}
		if matched > 0 {
			out = append(out, p)
		}
	}
	return out
}

// FormatOverview renders a summary grouped by region.
func FormatOverview(points []Point, lang shared.Language) string {
	if len(points) == 0 {
		return emptyMessage(lang)
	}
	regions := map[string]int{}
	for _, p := range points {
		r := p.regionName
		if r == "" {
			r = "Boshqa"
		}
		regions[r]++
	}
	var b strings.Builder
	switch lang.Code() {
	case shared.LangRu.Code():
		b.WriteString(fmt.Sprintf("Всего пунктов выдачи: %d\n", len(points)))
	case shared.LangEn.Code():
		b.WriteString(fmt.Sprintf("Total pickup points: %d\n", len(points)))
	default:
		b.WriteString(fmt.Sprintf("Jami topshirish punktlari: %d ta\n", len(points)))
	}
	for r, n := range regions {
		b.WriteString(fmt.Sprintf("• %s — %d ta\n", r, n))
	}
	b.WriteString("\n")
	b.WriteString(hintMessage(lang))
	return strings.TrimSpace(b.String())
}

// FormatRegionList renders detailed points for one region filter result.
func FormatRegionList(points []Point, lang shared.Language) string {
	if len(points) == 0 {
		return emptyMessage(lang)
	}
	var b strings.Builder
	region := points[0].regionName
	if region == "" {
		region = "Topshirish punktlari"
	}
	b.WriteString(region)
	b.WriteString(":\n")
	limit := len(points)
	if limit > 8 {
		limit = 8
	}
	for i := 0; i < limit; i++ {
		p := points[i]
		line := fmt.Sprintf("%d. %s (%s)", i+1, p.name, p.typeLabel)
		if p.address != "" {
			line += "\n   " + p.address
		}
		if p.phone != "" {
			line += "\n   ☎ " + p.phone
		}
		b.WriteString(line)
		b.WriteByte('\n')
	}
	return strings.TrimSpace(b.String())
}

func emptyMessage(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Пункты выдачи не найдены."
	case shared.LangEn.Code():
		return "No pickup points found."
	default:
		return "Topshirish punktlari topilmadi."
	}
}

func hintMessage(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Укажите город или область для подробного списка."
	case shared.LangEn.Code():
		return "Send a city or region name for a detailed list."
	default:
		return "Shahar yoki viloyat nomini yuboring — ro'yxatni ko'rsataman."
	}
}
