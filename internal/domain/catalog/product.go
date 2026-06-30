// Package catalog holds pure domain types and presenters for 1688 product search
// and category browsing.
package catalog

import (
	"fmt"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// Product is a value object for one search result item.
type Product struct {
	title    string
	picURL   string
	priceCNY float64
	priceUZS float64
	sales    int
	deeplink string
}

// NewProduct constructs a Product.
func NewProduct(title, picURL string, priceCNY, priceUZS float64, sales int, deeplink string) Product {
	return Product{title: title, picURL: picURL, priceCNY: priceCNY, priceUZS: priceUZS, sales: sales, deeplink: deeplink}
}

func (p Product) Title() string     { return p.title }
func (p Product) PicURL() string    { return p.picURL }
func (p Product) PriceCNY() float64 { return p.priceCNY }
func (p Product) PriceUZS() float64 { return p.priceUZS }
func (p Product) Sales() int        { return p.sales }
func (p Product) Deeplink() string  { return p.deeplink }

// FormatProductList renders a numbered plain-text list for chat (market + telegram).
func FormatProductList(products []Product, lang shared.Language, seeAllURL string) string {
	if len(products) == 0 {
		return notFoundMessage(lang)
	}
	var b strings.Builder
	b.WriteString(headerMessage(lang))
	for i, p := range products {
		line := fmt.Sprintf("%d. %s", i+1, p.title)
		if p.priceUZS > 0 {
			line += fmt.Sprintf(" — %.0f so'm", p.priceUZS)
		} else if p.priceCNY > 0 {
			line += fmt.Sprintf(" — %.0f CNY", p.priceCNY)
		}
		if p.sales > 0 {
			line += fmt.Sprintf(" (%d sotuv)", p.sales)
		}
		if p.deeplink != "" {
			line += "\n   " + p.deeplink
		}
		b.WriteString(line)
		b.WriteByte('\n')
	}
	if seeAllURL != "" {
		b.WriteString("\n")
		b.WriteString(seeAllMessage(lang))
		b.WriteString(": ")
		b.WriteString(seeAllURL)
	}
	return strings.TrimSpace(b.String())
}

func headerMessage(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Найденные товары:\n"
	case shared.LangEn.Code():
		return "Products found:\n"
	default:
		return "Topilgan mahsulotlar:\n"
	}
}

func seeAllMessage(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Смотреть все"
	case shared.LangEn.Code():
		return "See all"
	default:
		return "Barchasini ko'rish"
	}
}

func notFoundMessage(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Товары не найдены. Попробуйте другой запрос."
	case shared.LangEn.Code():
		return "No products found. Try a different query."
	default:
		return "Mahsulot topilmadi. Boshqa so'z bilan qidiring."
	}
}

func categoriesNotFoundMessage(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Категории временно недоступны. Попробуйте позже."
	case shared.LangEn.Code():
		return "Categories are temporarily unavailable. Please try again later."
	default:
		return "Kategoriyalar hozircha mavjud emas. Keyinroq urinib ko'ring."
	}
}

// Category is a node in the 1688 category tree.
type Category struct {
	id       int64
	name     string
	parentID int64
}

func NewCategory(id, parentID int64, name string) Category {
	return Category{id: id, name: name, parentID: parentID}
}

func (c Category) ID() int64       { return c.id }
func (c Category) Name() string    { return c.name }
func (c Category) ParentID() int64 { return c.parentID }

// FormatRootCategories renders top-level categories as a text list with deeplink hint.
func FormatRootCategories(cats []Category, lang shared.Language, searchBase string) string {
	if len(cats) == 0 {
		return categoriesNotFoundMessage(lang)
	}
	var b strings.Builder
	switch lang.Code() {
	case shared.LangRu.Code():
		b.WriteString("Категории:\n")
	case shared.LangEn.Code():
		b.WriteString("Categories:\n")
	default:
		b.WriteString("Kategoriyalar:\n")
	}
	limit := len(cats)
	if limit > 15 {
		limit = 15
	}
	for i := 0; i < limit; i++ {
		b.WriteString(fmt.Sprintf("%d. %s\n", i+1, cats[i].name))
	}
	if searchBase != "" {
		b.WriteString("\n")
		b.WriteString(seeAllMessage(lang))
		b.WriteString(": ")
		b.WriteString(searchBase)
	}
	return strings.TrimSpace(b.String())
}
