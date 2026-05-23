from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.domain.conversation_thread import (
    describe_previous_topic,
    infer_topic_from_assistant_text,
)
from app.domain.entities import Message
from app.domain.enums import MessageRole


def _msg(role: str, content: str) -> Message:
    return Message(
        id=uuid4(),
        session_id=uuid4(),
        role=role,
        content=content,
        msg_type=None,
        created_at=datetime.now(timezone.utc),
    )


def test_infer_pickup_from_assistant():
    text = "📍 Sahiy topshirish punktlari\n🏪 Filial: 18 ta\nViloyatni tanlang"
    assert infer_topic_from_assistant_text(text) == "pickup"


def test_infer_category_from_assistant():
    text = "📂 Sahiy katalog bo'limlari. Keraklisini tanlang:"
    assert infer_topic_from_assistant_text(text) == "category"


def test_describe_previous_topic_from_history():
    recent = [
        _msg(MessageRole.USER.value, "navoiy filial"),
        _msg(
            MessageRole.ASSISTANT.value,
            "📍 Navoiy\n🏪 Filial\nBoshqa viloyat: pastdagi tugmalardan tanlang.",
        ),
    ]
    prev = describe_previous_topic(recent)
    assert prev is not None
    assert prev["key"] == "pickup"
