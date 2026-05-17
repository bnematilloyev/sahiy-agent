"""Detect whether a message is in Sahiy support scope or needs an operator."""

from __future__ import annotations

from app.domain.constants import OFF_TOPIC_KEYWORDS, OPERATOR_REQUEST_PHRASES, SUPPORT_QUESTION_HINTS
from app.domain.text_normalize import normalize_text as _normalize_text


def is_operator_request(text: str) -> bool:
    lowered = _normalize_text(text)
    return any(phrase in lowered for phrase in OPERATOR_REQUEST_PHRASES)


def is_off_topic(text: str) -> bool:
    """True when the message is clearly outside Sahiy customer support."""
    if is_operator_request(text):
        return False

    lowered = _normalize_text(text)
    if any(hint in lowered for hint in SUPPORT_QUESTION_HINTS):
        return False

    return any(keyword in lowered for keyword in OFF_TOPIC_KEYWORDS)
