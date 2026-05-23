from __future__ import annotations

from app.domain.category_present import build_category_keyboard, parse_category_callback
from app.infrastructure.sahiy_api.categories_1688 import Category1688


def _cat(cat_id: int) -> Category1688:
    return Category1688(
        id=cat_id,
        ali_category_id=cat_id,
        ali_parent_id=0,
        name_cn="x",
        name_en="x",
        name_uz=f"Kategoriya {cat_id}",
        name_ru="x",
        leaf=0,
        level=1,
    )


def test_parse_category_callbacks():
    assert parse_category_callback("ct_o_42_0") == ("o", 42, 0)
    assert parse_category_callback("ct_o_42_100") == ("o", 42, 100)
    assert parse_category_callback("ct_b_0") == ("b", 0, 0)
    assert parse_category_callback("ct_b_100") == ("b", 100, 0)


def test_build_category_keyboard_open_includes_back():
    rows = build_category_keyboard([_cat(1), _cat(2)], "uz_lat", back_target=0, current_list_parent=100)
    flat = [btn for row in rows for btn in row]
    assert any("ct_o_1_100" in b["callback_data"] for b in flat)
    assert any(b["callback_data"] == "ct_b_0" for b in flat)
