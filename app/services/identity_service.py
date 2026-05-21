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
    validate_uzbek_phone,
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
        normalized = validate_uzbek_phone(phone)
        if not normalized:
            return PhoneVerifyResult(ok=False, error="invalid_format")

        api = get_sahiy_customer_api()
        if api is None:
            return PhoneVerifyResult(ok=False, error="api_unavailable")

        user_id = await api.find_user_id_by_phone(normalized)
        if user_id is None:
            logger.info("Phone %s not found in Sahiy", normalized)
            return PhoneVerifyResult(ok=False, error="not_found", phone=normalized)

        return PhoneVerifyResult(ok=True, phone=normalized, sahiy_user_id=user_id)

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
