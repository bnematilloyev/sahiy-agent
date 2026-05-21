from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import config
from app.db.models import MessageModel
from app.domain.enums import MessageRole
from app.repositories.message_repository import MessageRepository
from app.repositories.session_repository import ChatSessionRepository
from app.services.chat_service import ChatService
from app.services.factory import create_chat_service

pytestmark = pytest.mark.asyncio


async def test_is_idle_when_last_message_old(db_session: AsyncSession, monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_HOURS", "24")
    config.get_settings.cache_clear()

    sessions = ChatSessionRepository(db_session)
    messages = MessageRepository(db_session)
    user_id = f"idle-{uuid.uuid4()}"

    session = await sessions.create(user_id=user_id, channel="telegram")
    await messages.create(session.id, MessageRole.USER.value, "Salom")
    await db_session.flush()

    old_time = datetime.now(timezone.utc) - timedelta(hours=25)
    await db_session.execute(
        update(MessageModel)
        .where(MessageModel.session_id == session.id)
        .values(created_at=old_time)
    )
    await db_session.flush()

    assert await sessions.is_idle(session.id) is True


async def test_is_not_idle_for_recent_message(db_session: AsyncSession, monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_HOURS", "24")
    config.get_settings.cache_clear()

    sessions = ChatSessionRepository(db_session)
    messages = MessageRepository(db_session)
    user_id = f"active-{uuid.uuid4()}"

    session = await sessions.create(user_id=user_id, channel="telegram")
    await messages.create(session.id, MessageRole.USER.value, "Salom")
    await db_session.flush()

    assert await sessions.is_idle(session.id) is False


async def test_chat_opens_new_session_after_idle(db_session: AsyncSession, monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_HOURS", "24")
    config.get_settings.cache_clear()

    sessions = ChatSessionRepository(db_session)
    messages = MessageRepository(db_session)
    user_id = f"rotate-{uuid.uuid4()}"

    first = await sessions.create(user_id=user_id, channel="telegram")
    await messages.create(first.id, MessageRole.USER.value, "Eski savol")
    await db_session.flush()

    old_time = datetime.now(timezone.utc) - timedelta(hours=30)
    await db_session.execute(
        update(MessageModel)
        .where(MessageModel.session_id == first.id)
        .values(created_at=old_time)
    )
    await db_session.flush()

    chat = create_chat_service(db_session)
    await chat.reply(user_id=user_id, text="Yangi savol", channel="telegram")
    await db_session.commit()

    active = await sessions.get_active(user_id, "telegram")
    closed = await sessions.get_by_id(first.id)
    assert active is not None
    assert closed is not None
    assert active.id != first.id
    assert closed.status == "closed"
