from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.conversation_route import ConversationRoute, RouteDecision
from app.domain.dto import ChatContext
from app.domain.entities import Message
from app.domain.enums import MessageRole
from app.services.conversation_router import (
    ConversationRouterService,
    _reconcile_llm_with_signals,
)


def _msg(role: str, content: str) -> Message:
    return Message(
        id=uuid4(),
        session_id=uuid4(),
        role=role,
        content=content,
        msg_type=None,
        created_at=datetime.now(timezone.utc),
    )


class _StubAi:
    is_available = True

    def __init__(self, raw: str) -> None:
        self._raw = raw

    async def complete(self, system: str, user: str, *, max_tokens: int = 120) -> str:
        assert "MAVZU ALMASHISHI" in system
        assert "Oldingi mavzu" in user
        return self._raw


@pytest.mark.asyncio
async def test_llm_runs_after_pickup_thread_not_heuristic_pickup():
    """Pickup thread bor, lekin kategoriya savoli — LLM category tanlaydi."""
    recent = [
        _msg(MessageRole.USER.value, "navoiy filial qayerda"),
        _msg(
            MessageRole.ASSISTANT.value,
            "📍 Sahiy topshirish punktlari\nViloyatni tanlang",
        ),
    ]
    ai = _StubAi('{"route":"category","search_query":""}')
    router = ConversationRouterService(ai)
    ctx = ChatContext(
        session_id=uuid4(),
        user_id="u1",
        text="qanday turdagi mahsulot sotasizlar",
        channel="telegram",
        recent_messages=recent,
        metadata={},
    )
    decision = await router.decide(ctx)
    assert decision.route == ConversationRoute.CATEGORY


@pytest.mark.asyncio
async def test_reconcile_llm_pickup_to_category():
    recent = [
        _msg(
            MessageRole.ASSISTANT.value,
            "📍 Sahiy topshirish punktlari",
        ),
    ]
    out = _reconcile_llm_with_signals(
        "qanday kategoriyalar bor",
        recent,
        RouteDecision(route=ConversationRoute.PICKUP),
    )
    assert out.route == ConversationRoute.CATEGORY
