"""Suhbat tarixidan oldingi mavzuni taxmin qilish (router LLM uchun kontekst)."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from app.domain.entities import Message
from app.domain.enums import MessageRole
from app.domain.text_normalize import normalize_text

# (topic_key, assistant marker substrings)
_ASSISTANT_TOPIC_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "pickup",
        (
            "sahiy topshirish punktlari",
            "topshirish punktlari",
            "viloyatni tanlang",
            "postomat",
            "filial punktlari",
            "boshqa viloyat",
        ),
    ),
    (
        "category",
        (
            "katalog bo'limlari",
            "katalog boʻlimlari",
            "keraklisini tanlang",
            "mos bo'limlar",
            "ichki bo'limlar",
        ),
    ),
    (
        "product_search",
        (
            "bo'yicha topildi",
            "boyicha topildi",
            "qidiruv",
            "hammasini ko'rish",
            "sotib olish",
        ),
    ),
    (
        "api",
        (
            "buyurtma holati",
            "track",
            "zakaz",
            "yetkazib berish holati",
        ),
    ),
)

_TOPIC_LABELS = {
    "pickup": "Topshirish punktlari (filial/postomat)",
    "category": "Katalog kategoriyalari",
    "product_search": "Mahsulot qidiruvi",
    "api": "Buyurtma / track",
    "faq": "Umumiy FAQ",
    "ticket": "Operator / shikoyat",
    "chitchat": "Salomlashuv",
    "unknown": "Noma'lum",
}


def infer_topic_from_assistant_text(content: str) -> Optional[str]:
    lowered = normalize_text(content or "")
    if not lowered:
        return None
    if lowered.startswith("📍") and any(
        m in lowered for m in ("filial", "postomat", "punkt", "viloyat")
    ):
        return "pickup"
    if lowered.startswith("📂") or "katalog" in lowered:
        return "category"
    if lowered.startswith("🔍") and "topildi" in lowered:
        return "product_search"
    for key, markers in _ASSISTANT_TOPIC_MARKERS:
        if any(m in lowered for m in markers):
            return key
    return None


def describe_previous_topic(
    recent_messages: Sequence[Message],
    *,
    lookback: int = 6,
) -> Optional[dict[str, str]]:
    """Oxirgi yordamchi javob asosida oldingi mavzu."""
    tail = list(recent_messages)[-lookback:]
    for msg in reversed(tail):
        if msg.role != MessageRole.ASSISTANT.value:
            continue
        topic = infer_topic_from_assistant_text(msg.content or "")
        if topic:
            return {
                "key": topic,
                "label": _TOPIC_LABELS.get(topic, topic),
            }
    return None


def format_thread_hint_for_router(recent_messages: Sequence[Message]) -> str:
    prev = describe_previous_topic(recent_messages)
    if prev is None:
        return "Oldingi mavzu: yangi suhbat yoki aniqlanmadi."
    return (
        f"Oldingi mavzu (yordamchining oxirgi javobi): {prev['label']}. "
        "Agar mijoz boshqa narsa so'rasa — joriy xabar muhimroq."
    )
