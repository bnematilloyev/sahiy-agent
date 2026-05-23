"""Katalog / kategoriya bo'yicha savollarni aniqlash."""

from __future__ import annotations

import re

from app.domain.order_refs import extract_track
from app.domain.pickup_keywords import is_pickup_points_question
from app.domain.product_search_intent import is_product_search_intent
from app.domain.text_normalize import normalize_text

_CATEGORY_SIGNALS = (
    "kategoriya",
    "kategoriyalar",
    "kategoriyasi",
    "bo'lim",
    "bolim",
    "bo'limlar",
    "bolimlar",
    "katalog",
    "catalog",
    "turkum",
    "razdel",
    "razdely",
    "otdel",
    "категори",
    "раздел",
    "каталог",
    "category",
    "categories",
)

_VAGUE_CATALOG_PHRASES = (
    "qanday tovarlar",
    "qanday mahsulot",
    "qanday tovar",
    "nima sotiladi",
    "nimalar bor",
    "nima bor",
    "tovar turi",
    "mahsulot turi",
    "boshqa tovar",
    "boshqa mahsulot",
    "qaysi tovarlar",
    "qaysi mahsulot",
    "какие товары",
    "что продается",
    "что есть",
    "what products",
    "what do you sell",
)

_SPECIFIC_PRODUCT_RE = re.compile(
    r"\b(lego|kitob|kiyim|telefon|sumka|oyinchoq|noutbuk|kepka|parfum|"
    r"velosiped|quloqchin|smartfon|futbolka)\b",
    re.IGNORECASE,
)


def is_vague_catalog_question(text: str) -> bool:
    """Aniq mahsulot nomi yo'q, katalog / tur haqida umumiy savol."""
    lowered = normalize_text(text or "")
    if len(lowered) < 3:
        return False
    if any(p in lowered for p in _VAGUE_CATALOG_PHRASES):
        return True
    if "bormi" in lowered and any(w in lowered for w in ("tovar", "mahsulot", "nima")):
        if not _SPECIFIC_PRODUCT_RE.search(lowered):
            return True
    return False


def is_category_browse_intent(text: str) -> bool:
    """Kategoriya ro'yxati yoki bo'lim tanlash kerak."""
    raw = (text or "").strip()
    if len(raw) < 2:
        return False
    if extract_track(raw):
        return False
    if is_pickup_points_question(raw):
        return False

    lowered = normalize_text(raw)
    if any(sig in lowered for sig in _CATEGORY_SIGNALS):
        return True
    return is_vague_catalog_question(raw)


def should_resolve_via_categories(text: str) -> bool:
    """
    Mahsulot qidiruvdan oldin kategoriya orqali yo'naltirish kerakmi.
    Aniq «lego», «kitob» kabi so'rovlar to'g'ridan-to'g'ri qidiruvga ketadi.
    """
    if not is_product_search_intent(text) and not is_category_browse_intent(text):
        return False
    if is_category_browse_intent(text) and not _SPECIFIC_PRODUCT_RE.search(
        normalize_text(text)
    ):
        return True
    return is_vague_catalog_question(text)
