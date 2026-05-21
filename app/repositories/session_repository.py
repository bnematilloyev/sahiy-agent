from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import ChatSessionModel, MessageModel
from app.domain.entities import ChatSession
from app.domain.enums import SessionStatus
from app.repositories.base import BaseRepository
from app.repositories.mappers import to_chat_session


class ChatSessionRepository(BaseRepository):
    async def create(
        self,
        user_id: str,
        channel: str,
        status: str = SessionStatus.ACTIVE.value,
        session_id: Optional[UUID] = None,
    ) -> ChatSession:
        model = ChatSessionModel(
            id=session_id or uuid.uuid4(),
            user_id=user_id,
            channel=channel,
            status=status,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return to_chat_session(model)

    async def get_by_id(self, session_id: UUID) -> Optional[ChatSession]:
        model = await self._session.get(ChatSessionModel, session_id)
        return to_chat_session(model) if model else None

    async def get_active(self, user_id: str, channel: str) -> Optional[ChatSession]:
        stmt = (
            select(ChatSessionModel)
            .where(
                ChatSessionModel.user_id == user_id,
                ChatSessionModel.channel == channel,
                ChatSessionModel.status == SessionStatus.ACTIVE.value,
            )
            .order_by(ChatSessionModel.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return to_chat_session(model) if model else None

    async def get_last_activity_at(self, session_id: UUID) -> datetime:
        stmt = select(func.max(MessageModel.created_at)).where(
            MessageModel.session_id == session_id,
        )
        result = await self._session.execute(stmt)
        last_message = result.scalar_one_or_none()
        if last_message is not None:
            return _as_utc(last_message)

        model = await self._session.get(ChatSessionModel, session_id)
        if model is None:
            raise ValueError(f"session {session_id} not found")
        return _as_utc(model.created_at)

    async def is_idle(self, session_id: UUID, idle_hours: Optional[float] = None) -> bool:
        hours = idle_hours if idle_hours is not None else get_settings().session_idle_hours
        if hours <= 0:
            return False
        last = await self.get_last_activity_at(session_id)
        return datetime.now(timezone.utc) - last > timedelta(hours=hours)

    async def open_session(self, user_id: str, channel: str) -> ChatSession:
        existing = await self.get_active(user_id, channel)
        if existing:
            return existing
        return await self.create(user_id=user_id, channel=channel)

    async def close(self, session_id: UUID) -> Optional[ChatSession]:
        model = await self._session.get(ChatSessionModel, session_id)
        if model is None:
            return None
        model.status = SessionStatus.CLOSED.value
        await self._session.flush()
        await self._session.refresh(model)
        return to_chat_session(model)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
