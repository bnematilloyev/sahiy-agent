from __future__ import annotations

import pytest

from app.domain.category_intent import wants_root_category_list
from app.domain.category_match import rank_categories, score_category
from app.infrastructure.sahiy_api.categories_1688 import Category1688
from app.services.category_resolution_service import (
    CategoryResolutionKind,
    CategoryResolutionService,
)


def _led_cat() -> Category1688:
    return Category1688(
        id=1,
        ali_category_id=1,
        ali_parent_id=0,
        name_cn="led",
        name_en="led",
        name_uz="Boshqa turdagi LED mahsulotlari",
        name_ru="LED",
        leaf=1,
        level=2,
    )


def test_wants_root_category_list_user_message():
    text = "qaysi turdagi mahsulotlar sotasizlar (kategoriyalar masalan)"
    assert wants_root_category_list(text)


def test_turdagi_does_not_score_led_category():
    cat = _led_cat()
    assert score_category(cat, "qaysi turdagi mahsulotlar sotasizlar (kategoriyalar masalan)", "uz_lat") == 0.0
    assert not rank_categories(
        [cat],
        "qaysi turdagi mahsulotlar sotasizlar (kategoriyalar masalan)",
        "uz_lat",
        min_score=2.0,
    )


@pytest.mark.asyncio
async def test_resolve_text_shows_root_list_for_catalog_question(monkeypatch):
    root = [
        Category1688(
            id=i,
            ali_category_id=i,
            ali_parent_id=0,
            name_cn=f"c{i}",
            name_en=f"c{i}",
            name_uz=f"Bo'lim {i}",
            name_ru=f"c{i}",
            leaf=0,
            level=1,
        )
        for i in range(1, 4)
    ]

    class FakeCategories:
        async def list_categories(self, *, parent_id=None, lang="uz_lat"):
            assert parent_id == 0
            return root

    svc = CategoryResolutionService(categories=FakeCategories())
    resolved = await svc.resolve_text(
        "qaysi turdagi mahsulotlar sotasizlar (kategoriyalar masalan)",
        "uz_lat",
    )
    assert resolved.kind == CategoryResolutionKind.LIST
    assert len(resolved.categories) == 3
    assert resolved.matched is False
