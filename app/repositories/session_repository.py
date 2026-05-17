from __future__ import annotations

import uuid
from typing import Optional
from uuid import UUID

from sqlalchemy import select

from app.db.models import ChatSessionModel
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
