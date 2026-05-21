from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ResponseType
from app.services.factory import create_chat_service

pytestmark = pytest.mark.asyncio


async def test_off_topic_creates_ticket(db_session: AsyncSession):
    chat = create_chat_service(db_session)
    user_id = f"tg-{uuid.uuid4()}"

    result = await chat.reply(
        user_id=user_id,
        text="Barsa bilan Real nechchi o'ynadi?",
        channel="telegram",
    )
    await db_session.commit()

    assert result.response_type == ResponseType.TICKET
    assert result.ticket_id is not None
    assert "Sahiy" in result.text
    assert "operator" in result.text.lower()


async def test_company_question_without_faq_uses_static_answer(db_session: AsyncSession):
    chat = create_chat_service(db_session)
    user_id = f"tg-{uuid.uuid4()}"

    result = await chat.reply(
        user_id=user_id,
        text="Sahiy qanday kompaniya?",
        channel="telegram",
    )
    await db_session.commit()

    assert result.response_type == ResponseType.AUTO
    assert "12" in result.text
    assert "million" in result.text.lower()
    assert result.ticket_id is None
