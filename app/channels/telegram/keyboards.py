"""Telegram reply keyboards."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

PHONE_BUTTON_TEXT = "📱 Telefon raqamni yuborish"


def phone_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(PHONE_BUTTON_TEXT, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


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
            if isinstance(btn, dict) and btn.get("text") and btn.get("callback_data"):
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
