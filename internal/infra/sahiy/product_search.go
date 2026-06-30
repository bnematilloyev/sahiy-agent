package sahiy

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/catalog"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

const productSearchPath = "/api/client/purchase/search/item"

var langToAPIHeader = map[string]string{
	"uz":  "uz_UZ",
	"cyr": "uz_UZ",
	"ru":  "ru_RU",
	"en":  "en_US",
	"zh":  "zh_CN",
}

// ProductSearchAPI searches 1688 products via the Sahiy client API.
type ProductSearchAPI struct {
	client          *Client
	goodsDeeplink   string
	searchDeeplink  string
	defaultPageSize int
	defaultSort     string
}

// NewProductSearchAPI constructs the product search client.
func NewProductSearchAPI(client *Client, goodsBase, searchBase string, pageSize int, sort string) *ProductSearchAPI {
	if pageSize <= 0 {
		pageSize = 4
	}
	return &ProductSearchAPI{
		client:          client,
		goodsDeeplink:   goodsBase,
		searchDeeplink:  strings.TrimRight(searchBase, "/"),
		defaultPageSize: pageSize,
		defaultSort:     sort,
	}
}

// Search returns products for keyword. rate is CNY→UZS for price conversion.
func (a *ProductSearchAPI) Search(ctx context.Context, keyword string, lang shared.Language, rate float64) ([]catalog.Product, error) {
	q := url.Values{
		"keyword": {strings.TrimSpace(keyword)},
		"page":    {"1"},
		"size":    {fmt.Sprintf("%d", a.defaultPageSize)},
	}
	if a.defaultSort != "" {
		q.Set("sort", a.defaultSort)
	}
	acceptLang := langToAPIHeader[lang.Code()]
	if acceptLang == "" {
		acceptLang = "uz_UZ"
	}
	var raw json.RawMessage
	if err := a.client.GetJSONWithHeaders(ctx, productSearchPath, q, map[string]string{"Accept-Language": acceptLang}, &raw); err != nil {
		return nil, err
	}
	return mapProducts(raw, a.goodsDeeplink, rate), nil
}

// BuildSeeAllURL returns a web search deeplink for the keyword.
func (a *ProductSearchAPI) BuildSeeAllURL(keyword string) string {
	if a.searchDeeplink == "" || strings.TrimSpace(keyword) == "" {
		return ""
	}
	return a.searchDeeplink + "?q=" + url.QueryEscape(strings.TrimSpace(keyword)) + "&platform=1688"
}

func mapProducts(raw json.RawMessage, goodsBase string, rate float64) []catalog.Product {
	rows := extractList(raw)
	out := make([]catalog.Product, 0, len(rows))
	for _, row := range rows {
		title := rawStrFromMap(row, "title", "name")
		pic := rawStrFromMap(row, "pic_url", "picUrl", "image")
		detail := rawStrFromMap(row, "detail_url", "detailUrl", "url")
		price := rawFloatFromMap(row, "price", "direct_price", "directPrice")
		if price == 0 {
			price = rawFloatFromMap(row, "direct_price_cny", "price_cny")
		}
		sales := rawIntFromMap(row, "sales", "sold")
		deeplink := buildGoodsDeeplink(goodsBase, detail)
		uzs := price * rate
		out = append(out, catalog.NewProduct(title, pic, price, uzs, sales, deeplink))
	}
	return out
}

func buildGoodsDeeplink(base, detailURL string) string {
	if detailURL == "" {
		return ""
	}
	base = strings.TrimSpace(base)
	if strings.HasSuffix(base, "=") {
		return base + url.QueryEscape(detailURL)
	}
	if strings.Contains(base, "?") {
		return base + url.QueryEscape(detailURL)
	}
	return base + "?u=" + url.QueryEscape(detailURL)
}
