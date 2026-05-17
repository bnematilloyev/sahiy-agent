from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import SessionAccessDeniedError, SessionClosedError
from app.domain.enums import MessageRole, ResponseType, SessionStatus
from app.repositories.message_repository import MessageRepository
from app.repositories.session_repository import ChatSessionRepository
from app.services.chat_service import ChatService
from app.services.factory import create_chat_service
from tests.fixtures.faq import DEFAULT_FAQ_QUESTION, seed_single_delivery_faq

pytestmark = pytest.mark.asyncio


async def test_reply_to_faq(db_session: AsyncSession):
    await seed_single_delivery_faq(db_session)
    chat = create_chat_service(db_session)
    user_id = f"tg-{uuid.uuid4()}"

    result = await chat.reply(user_id=user_id, text=DEFAULT_FAQ_QUESTION, channel="telegram")
    await db_session.commit()

    assert result.response_type == ResponseType.AUTO
    assert len(result.text) > 5

    session = await ChatSessionRepository(db_session).get_active(user_id, "telegram")
    assert session is not None
    messages = await MessageRepository(db_session).list_by_session(session.id)
    assert len(messages) == 2
    assert messages[0].role == MessageRole.USER.value


async def test_reset_session_closes_previous(db_session: AsyncSession):
    chat = create_chat_service(db_session)
    user_id = f"tg-{uuid.uuid4()}"

    await chat.reply(user_id=user_id, text="Salom", channel="telegram")
    first = await ChatSessionRepository(db_session).get_active(user_id, "telegram")

    await chat.reset_session(user_id=user_id, channel="telegram")
    await db_session.commit()

    second = await ChatSessionRepository(db_session).get_active(user_id, "telegram")
    assert first and second and first.id != second.id


async def test_rejects_wrong_user(db_session: AsyncSession):
    sessions = ChatSessionRepository(db_session)
    session = await sessions.create(user_id="owner", channel="api")
    await db_session.flush()

    chat = create_chat_service(db_session)
    with pytest.raises(SessionAccessDeniedError):
        await chat.reply(
            user_id="intruder",
            text="Salom",
            channel="api",
            session_id=session.id,
        )


async def test_rejects_closed_session(db_session: AsyncSession):
    sessions = ChatSessionRepository(db_session)
    session = await sessions.create(user_id="owner", channel="api")
    await sessions.close(session.id)
    await db_session.flush()

    chat = create_chat_service(db_session)
    with pytest.raises(SessionClosedError):
        await chat.reply(
            user_id="owner",
            text="Salom",
            channel="api",
            session_id=session.id,
        )
