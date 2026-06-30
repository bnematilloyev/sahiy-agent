// Package catalog provides application services for product search and category browse.
package catalog

import (
	"context"
	"fmt"
	"log/slog"

	domaincatalog "github.com/sahiy-backend/sahiy-agent/internal/domain/catalog"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// ProductSearcher is the port for 1688 product search.
type ProductSearcher interface {
	Search(ctx context.Context, keyword string, lang shared.Language, rate float64) ([]domaincatalog.Product, error)
	BuildSeeAllURL(keyword string) string
}

// RateProvider returns CNY→UZS rate.
type RateProvider interface {
	CNYToUZS(ctx context.Context) float64
}

// Result is a catalog handler outcome.
type Result struct {
	Text         string
	Confidence   shared.Confidence
	ChannelExtra map[string]any
}

// ProductSearchService answers product search queries.
type ProductSearchService struct {
	search ProductSearcher
	rates  RateProvider
	log    *slog.Logger
}

// NewProductSearchService constructs the service.
func NewProductSearchService(search ProductSearcher, rates RateProvider, log *slog.Logger) *ProductSearchService {
	return &ProductSearchService{search: search, rates: rates, log: log}
}

// Respond searches products and formats a text reply with deeplinks.
func (s *ProductSearchService) Respond(ctx context.Context, query string, lang shared.Language) (Result, error) {
	rate := s.rates.CNYToUZS(ctx)
	products, err := s.search.Search(ctx, query, lang, rate)
	if err != nil {
		s.log.Warn("catalog: product search failed", "error", err)
		return Result{
			Text:       domaincatalog.FormatProductList(nil, lang, ""),
			Confidence: shared.NewConfidence(0.3),
		}, nil
	}
	seeAll := s.search.BuildSeeAllURL(query)
	if len(products) == 0 {
		return Result{
			Text:       domaincatalog.FormatProductList(nil, lang, seeAll),
			Confidence: shared.NewConfidence(0.5),
		}, nil
	}
	return Result{
		Text:         domaincatalog.FormatProductListHeader(query, len(products), lang),
		Confidence:   shared.NewConfidence(0.9),
		ChannelExtra: domaincatalog.BuildProductSearchExtra(products, query, rate, seeAll),
	}, nil
}

// CategoryFetcher loads category tree data.
type CategoryFetcher interface {
	RootCategories(ctx context.Context) ([]domaincatalog.Category, error)
	Children(ctx context.Context, parentID int64) ([]domaincatalog.Category, error)
	FindByID(ctx context.Context, id int64) (domaincatalog.Category, bool, error)
}

// CategoryService answers category browse queries.
type CategoryService struct {
	categories CategoryFetcher
	searchBase string
	log        *slog.Logger
}

// NewCategoryService constructs the category service.
func NewCategoryService(categories CategoryFetcher, searchBase string, log *slog.Logger) *CategoryService {
	return &CategoryService{categories: categories, searchBase: searchBase, log: log}
}

// RespondOpen handles ct_o category callback — children keyboard or product search header.
func (s *CategoryService) RespondOpen(ctx context.Context, categoryID int64, lang shared.Language) (Result, error) {
	cat, ok, err := s.categories.FindByID(ctx, categoryID)
	if err != nil || !ok {
		return Result{Text: domaincatalog.FormatRootCategories(nil, lang, s.searchBase), Confidence: shared.NewConfidence(0.3)}, nil
	}
	children, err := s.categories.Children(ctx, categoryID)
	if err != nil {
		return Result{Text: domaincatalog.FormatRootCategories(nil, lang, s.searchBase), Confidence: shared.NewConfidence(0.3)}, nil
	}
	if len(children) > 0 {
		header := fmt.Sprintf("📂 %s — ichki bo'limlar:", cat.Name())
		return Result{
			Text:         header,
			Confidence:   shared.NewConfidence(0.9),
			ChannelExtra: domaincatalog.CategoryInlineExtra(domaincatalog.BuildCategoryKeyboard(children, lang)),
		}, nil
	}
	// Leaf category: return name as search hint (telegram will run product search).
	return Result{
		Text:       fmt.Sprintf("🔍 «%s» bo'limidagi mahsulotlar qidirilmoqda…", cat.Name()),
		Confidence: shared.NewConfidence(0.9),
	}, nil
}

// CategorySearchKeyword returns the category name for product search after leaf selection.
func (s *CategoryService) CategorySearchKeyword(ctx context.Context, categoryID int64) (string, error) {
	cat, ok, err := s.categories.FindByID(ctx, categoryID)
	if err != nil {
		return "", err
	}
	if !ok {
		return "", fmt.Errorf("category not found")
	}
	return cat.Name(), nil
}

func (s *CategoryService) Respond(ctx context.Context, _ string, lang shared.Language) (Result, error) {
	cats, err := s.categories.RootCategories(ctx)
	if err != nil {
		s.log.Warn("catalog: categories fetch failed", "error", err)
		return Result{
			Text:       domaincatalog.FormatRootCategories(nil, lang, s.searchBase),
			Confidence: shared.NewConfidence(0.3),
		}, nil
	}
	return Result{
		Text:         domaincatalog.CategoryListHeader(lang),
		Confidence:   shared.NewConfidence(0.9),
		ChannelExtra: domaincatalog.CategoryInlineExtra(domaincatalog.BuildCategoryKeyboard(cats, lang)),
	}, nil
}
