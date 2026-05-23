"""Mijoz matnini 1688 kategoriyalari bilan moslashtirish."""

from __future__ import annotations

import re
from typing import List, Sequence, Tuple

from app.domain.text_normalize import normalize_text
from app.infrastructure.sahiy_api.categories_1688 import Category1688, category_display_name

_STOP = frozenset(
    {
        "qanday",
        "qaysi",
        "qanaqa",
        "nima",
        "nimalar",
        "bor",
        "bormi",
        "mavjud",
        "mavjudmi",
        "sotiladi",
        "sotiladimi",
        "uchun",
        "kerak",
        "menga",
        "manga",
        "sizda",
        "sahiy",
        "tovar",
        "tovarlar",
        "mahsulot",
        "mahsulotlar",
        "boshqa",
        "ham",
        "yana",
        "ko'rsat",
        "korsat",
        "katalog",
        "kategoriya",
        "kategoriyalar",
        "bo'lim",
        "bolim",
        "turdagi",
        "sotasizlar",
        "sotasiz",
        "sotiladi",
        "masalan",
        "tur",
        "turi",
        "the",
        "and",
        "for",
    }
)


def _tokens(text: str) -> List[str]:
    lowered = normalize_text(text or "")
    out: List[str] = []
    for token in re.findall(r"[a-z0-9]+", lowered):
        if len(token) < 3 or token in _STOP:
            continue
        if token not in out:
            out.append(token)
    return out


def _name_blob(cat: Category1688) -> str:
    return normalize_text(
        " ".join(
            part
            for part in (
                cat.name_uz,
                cat.name_ru,
                cat.name_en,
                cat.name_cn,
            )
            if part
        )
    )


def score_category(cat: Category1688, query: str, lang: str) -> float:
    """0+ — qanchalik yuqori bo'lsa, shunchalik mos."""
    tokens = _tokens(query)
    if not tokens:
        return 0.0
    blob = _name_blob(cat)
    if not blob:
        return 0.0

    score = 0.0
    display = normalize_text(category_display_name(cat, lang))
    for token in tokens:
        if token in blob:
            score += 3.0
        if display and token in display:
            score += 1.5
        if len(token) >= 5 and any(token in part for part in blob.split()):
            score += 1.0
    return score


def rank_categories(
    categories: Sequence[Category1688],
    query: str,
    lang: str,
    *,
    min_score: float = 2.0,
    limit: int = 8,
) -> List[Tuple[float, Category1688]]:
    ranked: List[Tuple[float, Category1688]] = []
    for cat in categories:
        s = score_category(cat, query, lang)
        if s >= min_score:
            ranked.append((s, cat))
    ranked.sort(key=lambda x: (-x[0], category_display_name(x[1], lang)))
    return ranked[:limit]
