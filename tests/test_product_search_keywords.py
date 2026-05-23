from __future__ import annotations

import json

from app.services.product_search_keywords import (
    ProductSearchKeywords,
    _fallback_keywords,
    _parse_llm_json,
)


def test_parse_llm_json():
    raw = json.dumps(
        {"keyword_zh": "夏季 女装", "display_short": "yozgi kiyim"},
        ensure_ascii=False,
    )
    parsed = _parse_llm_json(raw)
    assert parsed is not None
    assert parsed.keyword_zh == "夏季 女装"
    assert parsed.display_short == "yozgi kiyim"


def test_fallback_strips_stopwords_and_maps_uz():
    parsed = _fallback_keywords(
        "menga yozgi kollesiya mahsulotlarining eng yaxshi sifatli va arzonini ko'rsat"
    )
    assert "夏季" in parsed.keyword_zh or "服装" in parsed.keyword_zh
    assert "menga" not in parsed.display_short
    assert len(parsed.display_short) < 80


def test_fallback_chinese_passthrough():
    parsed = _fallback_keywords("夏季女装")
    assert parsed.keyword_zh == "夏季女装"
