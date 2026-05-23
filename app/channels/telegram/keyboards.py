"""Telegram reply keyboards."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

from app.domain.telegram_menu import main_menu_button_texts

PHONE_BUTTON_TEXT = "📱 Telefon raqamni yuborish"

_PHONE_BUTTON: Dict[str, str] = {
    "uz_lat": "📱 Telefon raqamni yuborish",
    "uz_cyrl": "📱 Телефон рақамни юбориш",
    "ru": "📱 Отправить номер телефона",
    "en": "📱 Send phone number",
    "zh": "📱 发送电话号码",
}


def phone_request_keyboard(lang: str = "uz_lat") -> ReplyKeyboardMarkup:
    label = _PHONE_BUTTON.get(lang) or _PHONE_BUTTON.get("uz_lat", PHONE_BUTTON_TEXT)
    return ReplyKeyboardMarkup(
        [[KeyboardButton(label, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def main_menu_keyboard(lang: str = "uz_lat") -> ReplyKeyboardMarkup:
    """Asosiy menyu: 2×2 + mahsulot qidirish."""
    labels = main_menu_button_texts(lang)
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(labels["callback"]),
                KeyboardButton(labels["new_chat"]),
            ],
            [
                KeyboardButton(labels["language"]),
                KeyboardButton(labels["help"]),
            ],
            [KeyboardButton(labels["product_search"])],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def inline_keyboard_from_extra(extra: Optional[Dict[str, Any]]) -> Optional[InlineKeyboardMarkup]:
    if not extra:
        return None
    rows = extra.get("inline_keyboard")
    if not isinstance(rows, list) or not rows:
        return None
    markup_rows: List[List[InlineKeyboardButton]] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        buttons = []
        for btn in row:
            if not isinstance(btn, dict) or not btn.get("text"):
                continue
            if btn.get("url"):
                buttons.append(
                    InlineKeyboardButton(str(btn["text"]), url=str(btn["url"]))
                )
            elif btn.get("callback_data"):
                buttons.append(
                    InlineKeyboardButton(
                        str(btn["text"]),
                        callback_data=str(btn["callback_data"])[:64],
                    )
                )
        if buttons:
            markup_rows.append(buttons)
    if not markup_rows:
        return None
    return InlineKeyboardMarkup(markup_rows)
