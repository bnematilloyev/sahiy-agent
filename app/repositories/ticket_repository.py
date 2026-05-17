from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TicketModel
from app.domain.entities import Ticket
from app.domain.enums import TicketStatus
from app.repositories.base import BaseRepository
from app.repositories.mappers import to_ticket


class TicketRepository(BaseRepository):
    async def create(
        self,
        session_id: UUID,
        user_id: str,
        ticket_type: str,
        status: str = TicketStatus.OPEN.value,
    ) -> Ticket:
        model = TicketModel(
            session_id=session_id,
            user_id=user_id,
            type=ticket_type,
            status=status,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return to_ticket(model)

    async def get_by_id(self, ticket_id: UUID) -> Optional[Ticket]:
        model = await self._session.get(TicketModel, ticket_id)
        return to_ticket(model) if model else None

    async def update_status(
        self,
        ticket_id: UUID,
        status: str,
        operator_id: Optional[str] = None,
    ) -> Optional[Ticket]:
        model = await self._session.get(TicketModel, ticket_id)
        if model is None:
            return None
        model.status = status
        if operator_id is not None:
            model.operator_id = operator_id
        await self._session.flush()
        await self._session.refresh(model)
        return to_ticket(model)

    async def get_open_for_session(self, session_id: UUID) -> Optional[Ticket]:
        open_statuses = (TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value)
        stmt = (
            select(TicketModel)
            .where(
                TicketModel.session_id == session_id,
                TicketModel.status.in_(open_statuses),
            )
            .order_by(TicketModel.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return to_ticket(model) if model else None

    async def close_open_for_session(self, session_id: UUID) -> int:
        open_statuses = (TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value)
        stmt = select(TicketModel).where(
            TicketModel.session_id == session_id,
            TicketModel.status.in_(open_statuses),
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        for model in rows:
            model.status = TicketStatus.CLOSED.value
        if rows:
            await self._session.flush()
        return len(rows)

    async def list_by_session(self, session_id: UUID) -> List[Ticket]:
        stmt = (
            select(TicketModel)
            .where(TicketModel.session_id == session_id)
            .order_by(TicketModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [to_ticket(row) for row in result.scalars().all()]
