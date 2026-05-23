from __future__ import annotations

from app.domain.telegram_menu import (
    build_rating_inline_extra,
    is_main_menu_label,
    match_menu_action,
    parse_rating_callback,
)
from app.channels.telegram.keyboards import main_menu_keyboard


def test_match_menu_action_uz():
    assert match_menu_action("🔄 Yangi suhbat", "uz_lat") == "new_chat"
    assert match_menu_action("❓ Yordam", "uz_lat") == "help"


def test_match_menu_action_cross_language():
    assert match_menu_action("🔄 New chat", "uz_lat") == "new_chat"


def test_is_main_menu_label():
    assert is_main_menu_label("📞 Qayta qo'ng'iroq")
    assert not is_main_menu_label("Salom")


def test_rating_callback_parse():
    assert parse_rating_callback("rate_5") == 5
    assert parse_rating_callback("rate_0") is None
    assert parse_rating_callback("lang_uz") is None


def test_rating_inline_has_five_stars():
    extra = build_rating_inline_extra()
    row = extra["inline_keyboard"][0]
    assert len(row) == 5
    assert row[0]["callback_data"] == "rate_1"
    assert "⭐" in row[4]["text"]


def test_main_menu_keyboard_layout():
    kb = main_menu_keyboard("uz_lat")
    assert len(kb.keyboard) == 3
    assert "Mahsulot qidirish" in kb.keyboard[2][0].text


def test_match_product_search_action():
    assert match_menu_action("🔍 Mahsulot qidirish", "uz_lat") == "product_search"
