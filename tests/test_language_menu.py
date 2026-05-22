from app.domain.language_menu import (
    build_language_menu_extra,
    parse_language_callback,
)
from app.domain.reply_language import EN, RU, UZ_LAT, ZH


def test_parse_language_callbacks():
    assert parse_language_callback("lang_uz") == UZ_LAT
    assert parse_language_callback("lang_ru") == RU
    assert parse_language_callback("lang_en") == EN
    assert parse_language_callback("lang_zh") == ZH
    assert parse_language_callback("ord_all") is None


def test_build_language_menu_has_four_buttons():
    extra = build_language_menu_extra()
    rows = extra["inline_keyboard"]
    assert len(rows) == 2
    labels = [btn["text"] for row in rows for btn in row]
    assert len(labels) == 4
    assert any("🇺🇿" in t and "O'zbek" in t for t in labels)
    assert any("🇷🇺" in t and "Русский" in t for t in labels)
    assert any("🇬🇧" in t and "English" in t for t in labels)
    assert any("🇨🇳" in t and "中文" in t for t in labels)
