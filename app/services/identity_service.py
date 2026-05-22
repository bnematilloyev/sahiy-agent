"""Verify phone against Sahiy API and persist session identity markers."""

from __future__ import annotations

import logging
from uuid import UUID

from app.domain.customer_identity import (
    API_UNAVAILABLE_TEXT,
    INVALID_PHONE_FORMAT_TEXT,
    PhoneVerifyResult,
    PHONE_NOT_REGISTERED_TEXT,
    PHONE_VERIFIED_TEXT,
    SAHIY_USER_ID_VERIFIED_TEXT,
    sahiy_phone_search_candidates,
    validate_uzbek_phone,
)

SAHIY_USER_ID_INVALID_TEXT = (
    "❌ Sahiy user ID noto'g'ri.\n\n"
    "Masalan: 111111 yoki id 191052 — ilovadagi hisob raqamingizni yozing."
)

SAHIY_USER_ID_NOT_FOUND_TEXT = (
    "❌ Bu user ID bo'yicha mijoz topilmadi.\n\n"
    "Telefon raqamini yuboring yoki boshqa ID ni tekshirib ko'ring."
)
from app.domain.dto import ChatReply
from app.domain.enums import MessageRole, QuestionCategory, ResponseType
from app.domain.verified_phone import PHONE_MESSAGE_PREFIX, SAHIY_USER_MESSAGE_PREFIX
from app.infrastructure.sahiy_api.factory import get_sahiy_customer_api
from app.repositories.message_repository import MessageRepository

logger = logging.getLogger(__name__)


class IdentityService:
    def __init__(self, messages: MessageRepository) -> None:
        self._messages = messages

    async def verify_phone(self, phone: str) -> PhoneVerifyResult:
        candidates = sahiy_phone_search_candidates(phone)
        if not candidates:
            return PhoneVerifyResult(ok=False, error="invalid_format")

        api = get_sahiy_customer_api()
        if api is None:
            return PhoneVerifyResult(ok=False, error="api_unavailable")

        for candidate in candidates:
            user_id = await api.find_user_id_by_phone(candidate)
            if user_id is not None:
                logger.info("Phone %r -> Sahiy user_id=%s", candidate, user_id)
                stored_phone = validate_uzbek_phone(candidate) or candidate
                return PhoneVerifyResult(
                    ok=True,
                    phone=stored_phone,
                    sahiy_user_id=user_id,
                )

        logger.info("Phone %r not found in Sahiy (tried %s)", phone, candidates)
        return PhoneVerifyResult(ok=False, error="not_found", phone=candidates[0])

    async def persist_identity(
        self, session_id: UUID, phone: str, sahiy_user_id: int
    ) -> None:
        await self._messages.create(
            session_id=session_id,
            role=MessageRole.USER.value,
            content=f"{PHONE_MESSAGE_PREFIX}{phone}",
        )
        await self._messages.create(
            session_id=session_id,
            role=MessageRole.USER.value,
            content=f"{SAHIY_USER_MESSAGE_PREFIX}{sahiy_user_id}",
        )

    async def verify_sahiy_user_id(self, sahiy_user_id: int) -> bool:
        if sahiy_user_id < 1:
            return False
        api = get_sahiy_customer_api()
        if api is None:
            return True
        try:
            snapshot = await api.build_snapshot(sahiy_user_id)
            return snapshot.user_id == sahiy_user_id
        except Exception as exc:
            logger.warning("Sahiy user_id=%s verify failed: %s", sahiy_user_id, exc)
            return False

    async def register_sahiy_user_id_in_session(
        self, session_id: UUID, sahiy_user_id: int
    ) -> tuple[Optional[int], Optional[ChatReply]]:
        if sahiy_user_id < 1:
            return None, self._reply(SAHIY_USER_ID_INVALID_TEXT)

        if not await self.verify_sahiy_user_id(sahiy_user_id):
            return None, self._reply(SAHIY_USER_ID_NOT_FOUND_TEXT)

        await self._messages.create(
            session_id=session_id,
            role=MessageRole.USER.value,
            content=f"{SAHIY_USER_MESSAGE_PREFIX}{sahiy_user_id}",
        )
        return sahiy_user_id, None

    async def register_phone_in_session(
        self, session_id: UUID, phone: str
    ) -> tuple[Optional[int], Optional[ChatReply]]:
        """
        Validate phone, lookup Sahiy user_id, save to session.
        Returns (sahiy_user_id, error_reply) — error_reply set on failure.
        """
        result = await self.verify_phone(phone)
        if result.error == "invalid_format":
            return None, self._reply(INVALID_PHONE_FORMAT_TEXT)
        if result.error == "api_unavailable":
            return None, self._reply(API_UNAVAILABLE_TEXT)
        if result.error == "not_found":
            return None, self._reply(PHONE_NOT_REGISTERED_TEXT)
        if not result.ok or result.sahiy_user_id is None or not result.phone:
            return None, self._reply(PHONE_NOT_REGISTERED_TEXT)

        await self.persist_identity(session_id, result.phone, result.sahiy_user_id)
        return result.sahiy_user_id, None

    @staticmethod
    def _reply(text: str) -> ChatReply:
        return ChatReply(
            response_type=ResponseType.AUTO,
            text=text,
            category=QuestionCategory.FAQ,
        )

    @staticmethod
    def verified_reply() -> ChatReply:
        return IdentityService._reply(PHONE_VERIFIED_TEXT)

    @staticmethod
    def verified_user_id_reply() -> ChatReply:
        return IdentityService._reply(SAHIY_USER_ID_VERIFIED_TEXT)
