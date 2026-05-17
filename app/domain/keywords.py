"""Shared keyword heuristics for classifier fallback and ticket typing."""

from __future__ import annotations

from app.domain.classification import (
    has_order_reference,
    is_concrete_incident,
    is_hypothetical_policy_question,
)
from app.domain.constants import SUPPORT_QUESTION_HINTS
from app.domain.scope import is_operator_request
from app.domain.text_normalize import normalize_text as _normalize_text

API_KEYWORDS = (
    "status",
    "holat",
    "qayerda",
    "kuzat",
    "tracking",
    "tovarim qayerda",
    "buyurtmam qayerda",
)

TICKET_KEYWORDS = (
    "shikoyat",
    "norozi",
    "operator kerak",
    "operatorga",
    "jonli operator",
)

CHITCHAT_KEYWORDS = (
    "salom",
    "assalom",
    "qalay",
    "rahmat",
    "yaxshimisiz",
    "nima gap",
    "tinch",
    "hay",
)

def classify_by_keywords(text: str) -> str:
    """Return faq | api | ticket for rule-based classification."""
    lowered = _normalize_text(text)

    if is_chitchat(text):
        return "faq"
    if has_order_reference(text):
        return "api"
    if is_concrete_incident(text) or is_operator_request(text):
        return "ticket"
    if is_hypothetical_policy_question(text):
        return "faq"
    if any(keyword in lowered for keyword in TICKET_KEYWORDS):
        return "ticket"
    if any(keyword in lowered for keyword in API_KEYWORDS):
        return "api"
    return "faq"


def is_chitchat(text: str) -> bool:
    lowered = _normalize_text(text)
    if not any(keyword in lowered for keyword in CHITCHAT_KEYWORDS):
        return False
    if any(hint in lowered for hint in SUPPORT_QUESTION_HINTS):
        return False
    return len(lowered) < 120


def infer_ticket_type(text: str) -> str:
    lowered = _normalize_text(text)
    if "qaytar" in lowered or "refund" in lowered:
        if is_concrete_incident(text):
            return "refund"
        return "complaint"
    if any(word in lowered for word in ("singan", "buzil", "brak")):
        return "broken"
    if any(
        phrase in lowered
        for phrase in ("kemagan", "kemadi", "yo'qol", "yetkaz", "ola olmadim")
    ):
        return "delivery"
    return "complaint"
