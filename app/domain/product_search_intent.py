"""Detect when the user wants Sahiy catalog / 1688 product search (not FAQ policy)."""

from __future__ import annotations

import re

from app.domain.classification import has_order_reference
from app.domain.order_refs import extract_track
from app.domain.pickup_keywords import is_pickup_points_question
from app.domain.text_normalize import normalize_text

# Mahsulot nomlari / kategoriyalar (lotin, kirill, rus, ingliz)
_PRODUCT_TERMS = (
    "lego",
    "лего",
    "kitob",
    "китоб",
    "книг",
    "book",
    "books",
    "oyinchoq",
    "o'yinchoq",
    "oyinchog",
    "ўйинчоқ",
    "игруш",
    "toy",
    "toys",
    "kepka",
    "kiyim",
    "ko'ylak",
    "shim",
    "futbolka",
    "krossovka",
    "poyabzal",
    "tufli",
    "sumka",
    "ryukzak",
    "telefon",
    "smartfon",
    "naushnik",
    "quloqchin",
    "soat",
    "kompyuter",
    "noutbuk",
    "planshet",
    "kolonka",
    "muzlatgich",
    "mashina",
    "avto",
    "velosiped",
    "samosval",
    "qalam",
    "daftar",
    "cosmetic",
    "kosmetik",
    "parfum",
    "atir",
    "sovg'a",
    "sovga",
    "mahsulot",
    "tovar",
    "catalog",
    "katalog",
)

# Xarid / qidiruv signallari
_SHOPPING_SIGNALS = (
    "kerak",
    "kerak edi",
    "xohlayman",
    "xohlay",
    "qidiryapman",
    "qidirmoqchiman",
    "qidirish",
    "qidirib",
    "topib bering",
    "toping",
    "ko'rsating",
    "korsating",
    "tavsiya",
    "rekomend",
    "recommend",
    "sotib olmoqchiman",
    "sotib olaman",
    "olib kelsangiz",
    "buy",
    "purchase",
    "looking for",
    "need a",
    "need an",
    "want to buy",
    "boshqa tovar",
    "boshqa mahsulot",
    "qanday tovar",
    "qanday mahsulot",
    "tovar turi",
    "mahsulot turi",
    "nima sotiladi",
    "nimalar bor",
)

# Mavjudligi haqida savol + mahsulot konteksti
_AVAILABILITY_RE = re.compile(
    r"\b(sotiladimi|sotiladi|sotiladimi|bormi|bor\s+mi|mavjudmi|mavjud\s+mi|"
    r"есть\s+ли|продается|продаётся|available|do you sell|do you have)\b",
    re.IGNORECASE,
)

_EXCLUDE_RE = re.compile(
    r"\b(buyurtma|zakaz|tracking|kuzat|holat|status|qayerda\s+kel|"
    r"qaytarish|vozvrat|refund|shikoyat|operator|filial|postomat|punkt)\b",
    re.IGNORECASE,
)


def is_product_search_intent(text: str) -> bool:
    """
    True when the user is shopping / asking about products in the Sahiy catalog.
    Excludes order tracking, pickup, refunds, and support incidents.
    """
    raw = (text or "").strip()
    if len(raw) < 2:
        return False
    if extract_track(raw) or has_order_reference(raw):
        return False
    if is_pickup_points_question(raw):
        return False

    lowered = normalize_text(raw)
    if _EXCLUDE_RE.search(lowered):
        # «buyurtmam qayerda» — buyurtma, mahsulot qidiruv emas
        if not any(term in lowered for term in _PRODUCT_TERMS):
            return False

    has_product_term = any(term in lowered for term in _PRODUCT_TERMS)
    has_shopping_signal = any(sig in lowered for sig in _SHOPPING_SIGNALS)
    has_availability = bool(_AVAILABILITY_RE.search(lowered)) and has_product_term

    if has_product_term and (has_shopping_signal or has_availability):
        return True

    # Qisqa mahsulot nomi: «lego», «kitob inglizcha»
    if has_product_term and len(lowered.split()) <= 8:
        if has_shopping_signal or has_availability or "ingliz" in lowered or "xitoy" in lowered:
            return True
        # «menga lego» / «lego o'yinchog'i»
        if "menga" in lowered or "manga" in lowered:
            return True

    return False
