from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import UUID

from app.core.config import get_settings
from app.core.exceptions import SessionAccessDeniedError, SessionClosedError
from app.domain.dto import ChatReply
from app.domain.entities import ChatSession
from app.domain.enums import SessionStatus
from app.repositories.ports import ChatSessionRepositoryPort, MessageRepositoryPort, TicketRepositoryPort
from app.services.identity_service import IdentityService
from app.services.reply_service import ReplyService


class ChatService:
    """
    Asosiy kirish nuqtasi: Sessiyani ochadi va ReplyService orqali javob qaytaradi.
    Barcha kanallar (Telegram, Go, Web) shu servisdan foydalanadi.
    """

    def __init__(
            self,
            sessions: ChatSessionRepositoryPort,
            replies: ReplyService,
            tickets: TicketRepositoryPort | None = None,
            messages: MessageRepositoryPort | None = None,
    ) -> None:
        self._sessions = sessions
        self._replies = replies
        self._tickets = tickets
        self._messages = messages

    async def reply(
            self,
            user_id: str,
            text: str,
            channel: str = "telegram",
            metadata: Optional[Dict[str, Any]] = None,
            session_id: Optional[UUID] = None,
            *,
            on_stream: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> ChatReply:
        """
        Xabarga javob qaytarishning asosiy oqimi.
        """
        # 1. Sessiyani ochish yoki yaratish
        session = await self._open_session(
            user_id=user_id,
            channel=channel,
            session_id=session_id,
        )

        # 2. Context tayyorlash (metadata + channel)
        ctx = {**(metadata or {}), "channel": channel}

        # 3. ReplyService orqali mantiqiy javobni shakllantirish
        # ReplyService ichida Classifier va FaqService chaqiriladi
        return await self._replies.reply(
            session_id=session.id,
            user_id=user_id,
            text=text,
            context=ctx,
            on_stream=on_stream,
        )

    async def reset_session(self, user_id: str, channel: str = "telegram") -> None:
        """
        Suhbatni yangilash (/new buyrug'i uchun).
        Eski sessiya va unga bog'liq ochiq ticketlarni yopadi.
        """
        active = await self._sessions.get_active(user_id, channel)
        if active:
            await self._close_session(active.id)

        await self._sessions.create(user_id=user_id, channel=channel)

    async def register_verified_phone(
        self,
        user_id: str,
        phone: str,
        channel: str = "telegram",
    ) -> tuple[Optional[int], Optional[str]]:
        """
        Validate phone format, verify in Sahiy API, persist PHONE/SAHIY_USER markers.
        Returns (sahiy_user_id, error_text).
        """
        if self._messages is None:
            return None, None
        session = await self._sessions.open_session(user_id=user_id, channel=channel)
        identity = IdentityService(self._messages)
        sahiy_user_id, err_reply = await identity.register_phone_in_session(session.id, phone)
        if err_reply is not None:
            return None, err_reply.text
        return sahiy_user_id, None

    async def register_sahiy_user_id(
        self,
        user_id: str,
        sahiy_user_id: int,
        channel: str = "telegram",
    ) -> tuple[Optional[int], Optional[str]]:
        """Persist SAHIY_USER marker. Returns (sahiy_user_id, error_text)."""
        if self._messages is None:
            return None, None
        session = await self._sessions.open_session(user_id=user_id, channel=channel)
        identity = IdentityService(self._messages)
        uid, err_reply = await identity.register_sahiy_user_id_in_session(
            session.id, sahiy_user_id
        )
        if err_reply is not None:
            return None, err_reply.text
        return uid, None

    async def _open_session(
            self,
            user_id: str,
            channel: str,
            session_id: Optional[UUID],
    ) -> ChatSession:
        """
        Sessiya xavfsizligini va holatini tekshiruvchi ichki metod.
        """
        # Agar session_id berilmagan bo'lsa, foydalanuvchining oxirgi faol sessiyasini topadi
        if session_id is None:
            await self._expire_idle_session_if_needed(user_id, channel)
            return await self._sessions.open_session(user_id=user_id, channel=channel)

        # Berilgan ID bo'yicha sessiyani qidirish
        session = await self._sessions.get_by_id(session_id)

        # Agar bunday sessiya bo'lmasa, yangisini yaratish
        if session is None:
            return await self._sessions.create(
                user_id=user_id,
                channel=channel,
                session_id=session_id,
            )

        # XAVFSIZLIK: Sessiya boshqa foydalanuvchiga tegishli emasligini tekshirish
        if session.user_id != user_id:
            raise SessionAccessDeniedError("Sessiya ushbu foydalanuvchiga tegishli emas")

        if session.status != SessionStatus.ACTIVE.value:
            raise SessionClosedError("Sessiya yopilgan")

        return session

    async def _expire_idle_session_if_needed(self, user_id: str, channel: str) -> None:
        if get_settings().session_idle_hours <= 0:
            return
        active = await self._sessions.get_active(user_id, channel)
        if active is None:
            return
        if await self._sessions.is_idle(active.id):
            await self._close_session(active.id)

    async def _close_session(self, session_id: UUID) -> None:
        if self._tickets:
            await self._tickets.close_open_for_session(session_id)
        await self._sessions.close(session_id)