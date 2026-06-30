package catalog_test

import (
	"testing"

	domaincatalog "github.com/sahiy-backend/sahiy-agent/internal/domain/catalog"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/channel"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

func TestBuildProductSearchExtra(t *testing.T) {
	products := []domaincatalog.Product{
		domaincatalog.NewProduct("Test", "http://pic", 10, 120000, 5, "http://buy"),
	}
	extra := domaincatalog.BuildProductSearchExtra(products, "kiyim", 12000, "http://search?q=kiyim")
	if extra[channel.KeyDisableStream] != true {
		t.Fatal("expected disable_stream")
	}
	items, ok := extra[channel.KeyProductSearchItems].([]map[string]any)
	if !ok || len(items) != 1 {
		t.Fatalf("items = %v", extra[channel.KeyProductSearchItems])
	}
	if extra[channel.KeyProductSearchSeeAllKeyword] != "kiyim" {
		t.Fatal("see all keyword")
	}
}

func TestBuildCategoryKeyboard(t *testing.T) {
	cats := []domaincatalog.Category{
		domaincatalog.NewCategory(1, 0, "Elektronika"),
		domaincatalog.NewCategory(2, 0, "Kiyim"),
	}
	kb := domaincatalog.BuildCategoryKeyboard(cats, shared.LangUz)
	if len(kb) == 0 {
		t.Fatal("expected keyboard rows")
	}
}
