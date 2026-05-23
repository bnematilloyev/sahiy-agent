"""Repository ports — swap implementations without touching service layer."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Protocol
from uuid import UUID

from app.domain.entities import ChatSession, FAQEntry, Message, Ticket


class ChatSessionRepositoryPort(Protocol):
    async def create(
        self,
        user_id: str,
        channel: str,
        status: str = "active",
        session_id: Optional[UUID] = None,
    ) -> ChatSession: ...

    async def get_by_id(self, session_id: UUID) -> Optional[ChatSession]: ...

    async def get_active(self, user_id: str, channel: str) -> Optional[ChatSession]: ...

    async def open_session(self, user_id: str, channel: str) -> ChatSession: ...

    async def close(self, session_id: UUID) -> Optional[ChatSession]: ...

    async def get_last_activity_at(self, session_id: UUID) -> datetime: ...

    async def is_idle(self, session_id: UUID, idle_hours: Optional[float] = None) -> bool: ...


class MessageRepositoryPort(Protocol):
    async def create(
        self,
        session_id: UUID,
        role: str,
        content: str,
        msg_type: Optional[str] = None,
    ) -> Message: ...

    async def list_by_session(self, session_id: UUID, limit: int = 50) -> List[Message]: ...

    async def get_recent(self, session_id: UUID, limit: int = 10) -> List[Message]: ...

    async def find_customer_identity(
        self, session_id: UUID, *, scan_limit: int = 100
    ) -> tuple[Optional[str], Optional[int]]: ...


class FAQRepositoryPort(Protocol):
    async def create(
        self,
        question: str,
        answer: str,
        category: str,
        embedding: List[float],
    ) -> FAQEntry: ...

    async def search_similar(
        self,
        embedding: List[float],
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> List[FAQEntry]: ...

    async def count(self) -> int: ...

    async def delete_all(self) -> int: ...


class TicketRepositoryPort(Protocol):
    async def create(
        self,
        session_id: UUID,
        user_id: str,
        ticket_type: str,
        status: str = "open",
    ) -> Ticket: ...

    async def get_by_id(self, ticket_id: UUID) -> Optional[Ticket]: ...

    async def get_open_for_session(self, session_id: UUID) -> Optional[Ticket]: ...

    async def update_status(
        self,
        ticket_id: UUID,
        status: str,
        operator_id: Optional[str] = None,
    ) -> Optional[Ticket]: ...

    async def list_by_session(self, session_id: UUID) -> List[Ticket]: ...

    async def close_open_for_session(self, session_id: UUID) -> int: ...
