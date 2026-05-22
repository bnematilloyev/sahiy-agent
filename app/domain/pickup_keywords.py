"""Detect pickup point / filial / postomat questions (incl. contextual follow-ups)."""

from __future__ import annotations

import re
from typing import List, Sequence

from app.domain.classification import has_order_reference
from app.domain.entities import Message
from app.domain.enums import MessageRole
from app.domain.customer_identity import extract_sahiy_user_id, is_identity_only_message
from app.domain.order_refs import extract_track
from app.domain.pickup_present import has_location_in_text
from app.domain.text_normalize import normalize_text

_PICKUP_KEYWORDS = (
    "punkt",
    "filial",
    "filiall",
    "filili",
    "postomat",
    "postamat",
    "olib ketish",
    "olib ketaman",
    "olib ketasiz",
    "qayerdan olaman",
    "qayerdan olib",
    "topshirish punkti",
    "berish punkti",
    "manzil punkt",
    "punktlar",
    "qayerda topshirish",
    "pickup",
    "nechta filial",
    "qayerlarda bor",
)

_PICKUP_THREAD_MARKERS = (
    "sahiy topshirish punktlari",
    "topshirish punktlari",
    "boshqa viloyat",
    "filial punktlari",
    "postomatlar",
    "viloyatni tanlang",
)

_FOLLOWUP_HINT_RE = re.compile(
    r"\b(chi|chu|dachi|ham|unda|yana|keyin|shunda)\b",
    re.IGNORECASE,
)

_ORDER_CONTEXT_WORDS = (
    "zakaz",
    "zakazim",
    "buyurtma",
    "buyurtmam",
    "buyurtmalar",
    "tovar",
    "tovarim",
    "tracking",
    "kuzat",
    "holat",
)

_SUPPORT_TOPIC_WORDS = (
    "siniq",
    "singan",
    "vozvrat",
    "qaytar",
    "refund",
    "brak",
    "shikoyat",
    "norozi",
    "buzil",
    "kemagan",
    "kemadi",
)


def is_identity_registration_text(text: str) -> bool:
    """«user ID 7991625» — filial emas, identifikatsiya."""
    return extract_sahiy_user_id(text) is not None and is_identity_only_message(text)


def is_support_or_order_topic(text: str) -> bool:
    """Buyurtma track, shikoyat, qaytarish — filial emas."""
    if extract_track(text) or has_order_reference(text):
        return True
    lowered = normalize_text(text)
    if any(w in lowered for w in _SUPPORT_TOPIC_WORDS):
        return True
    if any(w in lowered for w in _ORDER_CONTEXT_WORDS):
        return True
    return False


def is_order_status_question(text: str) -> bool:
    """Buyurtma qayerda / holati — filial emas."""
    if is_support_or_order_topic(text):
        lowered = normalize_text(text)
        if extract_track(text) or has_order_reference(text):
            return True
        if any(w in lowered for w in _SUPPORT_TOPIC_WORDS):
            return True
        if any(w in lowered for w in ("qayerda", "qayer", "qayda", "holat", "status", "kuzat", "tracking")):
            return True
        if any(w in lowered for w in _ORDER_CONTEXT_WORDS) and any(
            w in lowered
            for w in ("qayerda", "qayer", "qayda", "holat", "status", "kuzat", "tracking")
        ):
            return True
    return False


def is_pickup_points_question(text: str) -> bool:
    if is_identity_registration_text(text):
        return False
    if is_order_status_question(text):
        return False
    lowered = normalize_text(text)
    if any(k in lowered for k in _PICKUP_KEYWORDS):
        return True
    if "qayerda" in lowered and any(
        w in lowered for w in ("punkt", "filial", "filiall", "postomat", "olib", "bor")
    ):
        return True
    if "bormi" in lowered and any(w in lowered for w in ("filial", "filiall", "postomat", "punkt")):
        return True
    if "nechta" in lowered and any(w in lowered for w in ("filial", "filiall", "punkt", "postomat")):
        return True
    return False


def is_pickup_thread_active(recent_messages: Sequence[Message], *, lookback: int = 6) -> bool:
    """True if the last few turns were about filial/postomat (assistant or user)."""
    tail = list(recent_messages)[-lookback:]
    for msg in reversed(tail):
        content = normalize_text(msg.content)
        if msg.role == MessageRole.ASSISTANT.value:
            if any(m in content for m in _PICKUP_THREAD_MARKERS):
                return True
            if content.startswith("📍") and ("filial" in content or "postomat" in content or "punkt" in content):
                return True
        elif msg.role == MessageRole.USER.value:
            if is_pickup_points_question(msg.content):
                return True
    return False


def is_pickup_location_followup(text: str) -> bool:
    """Short continuation with a place name, e.g. 'toshkentdachi?', 'samarqandda ham'."""
    if is_support_or_order_topic(text):
        return False
    lowered = normalize_text(text).strip()
    if not lowered or len(lowered) > 80:
        return False
    words = lowered.split()
    if len(words) > 5:
        return False
    if has_location_in_text(lowered) and len(words) <= 4:
        return True
    if _FOLLOWUP_HINT_RE.search(lowered) and len(words) <= 4:
        return True
    return False


def is_pickup_conversation_turn(text: str, recent_messages: Sequence[Message]) -> bool:
    """Standalone pickup question or contextual follow-up in an active pickup thread."""
    if is_identity_registration_text(text):
        return False
    if is_support_or_order_topic(text):
        return False
    if is_pickup_points_question(text):
        return True
    if is_pickup_thread_active(recent_messages) and is_pickup_location_followup(text):
        return True
    return False


def build_pickup_query_text(text: str, recent_messages: Sequence[Message]) -> str:
    """
    Text used to resolve city/region — merges thread context when the user only
    sends a short follow-up ('toshkentdachi?').
    """
    if has_location_in_text(text):
        return text

    parts: List[str] = [text]
    for msg in reversed(recent_messages):
        if msg.role != MessageRole.USER.value:
            continue
        if is_pickup_points_question(msg.content) or has_location_in_text(msg.content):
            parts.insert(0, msg.content)
            break
    return " ".join(parts)
