"""Verified customer phone from Telegram contact or session history."""

from __future__ import annotations

from typing import Optional

from app.domain.dto import ChatContext
from app.domain.order_refs import normalize_phone

PHONE_MESSAGE_PREFIX = "PHONE:"
SAHIY_USER_MESSAGE_PREFIX = "SAHIY_USER:"


def verified_phone_from_context(context: ChatContext) -> Optional[str]:
    raw = context.metadata.get("verified_phone")
    if isinstance(raw, str) and raw.strip():
        return normalize_phone(raw)

    for msg in reversed(context.recent_messages):
        if msg.role != "user":
            continue
        if msg.content.startswith(PHONE_MESSAGE_PREFIX):
            return normalize_phone(msg.content[len(PHONE_MESSAGE_PREFIX) :])
    return None


def sahiy_user_id_from_context(context: ChatContext) -> Optional[int]:
    raw = context.metadata.get("sahiy_user_id")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass

    for msg in reversed(context.recent_messages):
        if msg.role != "user":
            continue
        if msg.content.startswith(SAHIY_USER_MESSAGE_PREFIX):
            try:
                return int(msg.content[len(SAHIY_USER_MESSAGE_PREFIX) :].strip())
            except ValueError:
                return None
    return None
