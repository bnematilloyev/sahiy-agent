from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Shared session handle for all repositories in a single unit of work."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
