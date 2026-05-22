"""Telegram inline tugmalar — javob tilini tanlash."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.domain.reply_language import EN, RU, UZ_LAT, ZH

CALLBACK_PREFIX = "lang"

LANGUAGE_PICKER_PROMPT = (
    "🌐 Tilni tanlang\n"
    "Выберите язык · Choose language · 选择语言"
)

# callback suffix -> reply_language code
_LANG_CODES: Dict[str, str] = {
    "uz": UZ_LAT,
    "ru": RU,
    "en": EN,
    "zh": ZH,
}

_LANG_BUTTONS: tuple[tuple[str, str, str], ...] = (
    ("uz", "🇺🇿", "O'zbek"),
    ("ru", "🇷🇺", "Русский"),
    ("en", "🇬🇧", "English"),
    ("zh", "🇨🇳", "中文"),
)


def build_language_menu_extra() -> Dict[str, Any]:
    """2×2 inline keyboard: UZ | RU / EN | CN."""
    row1: List[Dict[str, str]] = []
    row2: List[Dict[str, str]] = []
    for i, (code, flag, label) in enumerate(_LANG_BUTTONS):
        btn = {
            "text": f"{flag} {label}",
            "callback_data": f"{CALLBACK_PREFIX}_{code}",
        }
        if i < 2:
            row1.append(btn)
        else:
            row2.append(btn)
    return {"inline_keyboard": [row1, row2]}


def parse_language_callback(data: str) -> Optional[str]:
    """lang_uz → uz_lat; lang_zh → zh."""
    if not data or not data.startswith(f"{CALLBACK_PREFIX}_"):
        return None
    suffix = data[len(CALLBACK_PREFIX) + 1 :].strip().lower()
    return _LANG_CODES.get(suffix)
