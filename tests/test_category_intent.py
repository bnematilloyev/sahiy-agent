from __future__ import annotations

from app.domain.category_intent import (
    is_category_browse_intent,
    is_vague_catalog_question,
    should_resolve_via_categories,
    wants_root_category_list,
)
from app.domain.product_search_intent import is_product_search_intent


def test_vague_catalog_question():
    assert is_vague_catalog_question("kattalar uchun qanday tovarlar bor")
    assert is_category_browse_intent("qanday kategoriyalar bor")


def test_specific_product_not_vague():
    assert not is_vague_catalog_question("menga lego o'yinchog'i kerak")


def test_category_browse_intent():
    assert is_category_browse_intent("qanday kategoriyalar bor")
    assert is_category_browse_intent("kattalar uchun qanday tovarlar bor")


def test_order_not_category():
    assert not is_category_browse_intent("buyurtmalarim qayerda")


def test_katgoriya_typo_is_category_intent():
    assert is_category_browse_intent("qanday katgoriya")


def test_wants_root_for_sell_categories_question():
    assert wants_root_category_list(
        "qaysi turdagi mahsulotlar sotasizlar (kategoriyalar masalan)"
    )


def test_should_resolve_vague_not_lego():
    assert should_resolve_via_categories("kattalar uchun qanday tovarlar bor")
    assert is_product_search_intent("menga lego kerak")
    assert not should_resolve_via_categories("menga lego kerak")
