"""FastAPI dependency injection."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.services.chat_service import ChatService
from app.services.factory import create_chat_service


async def get_chat_service(
    session: AsyncSession = Depends(get_db_session),
) -> ChatService:
    return create_chat_service(session)
