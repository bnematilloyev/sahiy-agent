"""Intent helpers: hypothetical FAQ vs concrete incidents needing an operator."""

from __future__ import annotations

import re

from app.domain.scope import is_operator_request
from app.domain.text_normalize import normalize_text as _normalize_text

ORDER_REF_PATTERN = re.compile(
    r"\b(dg[-\s]?\d{4,}|ord[-\s]?\d+|yt\d+|jt\d+|78\d+)\b",
    re.IGNORECASE,
)

HYPOTHETICAL_MARKERS = (
    "kelsa",
    "bo'lsa",
    "bo'ladimi",
    "mumkinmi",
    "mumkin",
    "qilsam",
    "qilsa",
    "agar",
    "bormi",
    "beriladimi",
    "olamizmi",
    "olasizlarmi",
    "berasizlarmi",
    "qaytarasizlarmi",
    "qaytariladimi",
    "nima bo'ladi",
    "nima qilish",
    "qanday qil",
)

PAST_INCIDENT_MARKERS = (
    "keldi",
    "kelgan",
    "olib",
    "oldim",
    "yetkazildi",
    "yetkazdilar",
    "kecha",
    "bugun keldi",
    "foto",
    "rasm",
    "video",
    "surat",
    "kemagan",
    "kemadi",
    "yo'qolgan",
    "yo'qoldi",
    "qaytmadi",
    "qaymadi",
    "pul bermadi",
)

POLICY_TOPIC_MARKERS = (
    "qaytar",
    "refund",
    "singan",
    "buzil",
    "brak",
    "kafolat",
    "yetkaz",
    "to'lov",
    "kompaniya",
    "sahiy",
    "kafolat",
    "bekor",
    "almashtir",
)


def has_order_reference(text: str) -> bool:
    return bool(ORDER_REF_PATTERN.search(text))


def is_company_question(text: str) -> bool:
    lowered = _normalize_text(text)
    if "sahiy" not in lowered:
        return False
    return any(
        word in lowered
        for word in ("kompaniya", "nima", "qanday", "kim", "haqida", "do'kon", "dokon")
    )


def is_hypothetical_policy_question(text: str) -> bool:
    """e.g. 'singan kelsa qaytarasizlarmi?' — policy FAQ, not a live complaint."""
    if is_operator_request(text):
        return False
    lowered = _normalize_text(text)
    if not any(topic in lowered for topic in POLICY_TOPIC_MARKERS):
        return False
    if any(marker in lowered for marker in PAST_INCIDENT_MARKERS):
        return False
    if "?" in text:
        return True
    return any(marker in lowered for marker in HYPOTHETICAL_MARKERS)


def is_concrete_incident(text: str) -> bool:
    """Real problem that happened — route to ticket / operator."""
    if is_operator_request(text):
        return True
    lowered = _normalize_text(text)
    if is_hypothetical_policy_question(text):
        return False
    if not any(marker in lowered for marker in PAST_INCIDENT_MARKERS):
        return False
    incident_words = (
        "singan",
        "buzil",
        "brak",
        "noto'g'ri",
        "yo'qol",
        "kemagan",
        "kemadi",
        "qaytmadi",
        "qaymadi",
        "pul",
        "pulni",
        "shikoyat",
        "norozi",
    )
    return any(word in lowered for word in incident_words)
