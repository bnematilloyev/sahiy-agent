from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MessageModel
from app.domain.entities import Message
from app.domain.enums import MessageRole
from app.domain.order_refs import normalize_phone
from app.domain.verified_phone import PHONE_MESSAGE_PREFIX, SAHIY_USER_MESSAGE_PREFIX
from app.repositories.base import BaseRepository
from app.repositories.mappers import to_message


class MessageRepository(BaseRepository):
    async def create(
        self,
        session_id: UUID,
        role: str,
        content: str,
        msg_type: Optional[str] = None,
    ) -> Message:
        model = MessageModel(
            session_id=session_id,
            role=role,
            content=content,
            msg_type=msg_type,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return to_message(model)

    async def list_by_session(self, session_id: UUID, limit: int = 50) -> List[Message]:
        stmt = (
            select(MessageModel)
            .where(MessageModel.session_id == session_id)
            .order_by(
                MessageModel.created_at.asc(),
                case((MessageModel.role == MessageRole.USER.value, 0), else_=1),
                MessageModel.id.asc(),
            )
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [to_message(row) for row in result.scalars().all()]

    async def get_recent(self, session_id: UUID, limit: int = 10) -> List[Message]:
        stmt = (
            select(MessageModel)
            .where(MessageModel.session_id == session_id)
            .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return [to_message(row) for row in rows]

    async def find_customer_identity(
        self, session_id: UUID, *, scan_limit: int = 100
    ) -> tuple[Optional[str], Optional[int]]:
        """Latest PHONE: / SAHIY_USER: markers in session (survives bot restarts)."""
        stmt = (
            select(MessageModel)
            .where(MessageModel.session_id == session_id)
            .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
            .limit(scan_limit)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())

        phone: Optional[str] = None
        sahiy_user_id: Optional[int] = None
        for model in reversed(rows):
            content = model.content or ""
            if content.startswith(PHONE_MESSAGE_PREFIX):
                phone = normalize_phone(content[len(PHONE_MESSAGE_PREFIX) :])
            elif content.startswith(SAHIY_USER_MESSAGE_PREFIX):
                try:
                    sahiy_user_id = int(content[len(SAHIY_USER_MESSAGE_PREFIX) :].strip())
                except ValueError:
                    pass
        return phone, sahiy_user_id
