"""Verify phone against Sahiy API and persist session identity markers."""

from __future__ import annotations

import logging
from uuid import UUID

from app.domain.customer_identity import (
    PhoneVerifyResult,
    api_unavailable_text,
    invalid_phone_format_text,
    phone_not_registered_text,
    phone_verified_text,
    sahiy_phone_search_candidates,
    validate_uzbek_phone,
)

_SAHIY_USER_ID_INVALID: dict[str, str] = {
    "uz_lat": "❌ Sahiy user ID noto'g'ri.\n\nMasalan: 111111 yoki id 191052 — ilovadagi hisob raqamingizni yozing.",
    "uz_cyrl": "❌ Sahiy user ID нотўғри.\n\nМасалан: 111111 ёки id 191052 — иловадаги ҳисоб рақамингизни ёзинг.",
    "ru": "❌ Неверный Sahiy user ID.\n\nНапример: 111111 или id 191052 — напишите номер вашего аккаунта в приложении.",
    "en": "❌ Invalid Sahiy user ID.\n\nExample: 111111 or id 191052 — write your app account number.",
    "zh": "❌ Sahiy用户ID无效。\n\n示例：111111 或 id 191052 — 请填写您的应用账户编号。",
}

_SAHIY_USER_ID_NOT_FOUND: dict[str, str] = {
    "uz_lat": "❌ Bu user ID bo'yicha mijoz topilmadi.\n\nTelefon raqamini yuboring yoki boshqa ID ni tekshirib ko'ring.",
    "uz_cyrl": "❌ Бу user ID бўйича мижоз топилмади.\n\nТелефон рақамини юборинг ёки бошқа ID ни текшириб кўринг.",
    "ru": "❌ Клиент с таким user ID не найден.\n\nОтправьте номер телефона или проверьте другой ID.",
    "en": "❌ No customer found with this user ID.\n\nSend your phone number or check another ID.",
    "zh": "❌ 未找到该用户ID对应的客户。\n\n请发送电话号码或检查其他ID。",
}
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
        self, session_id: UUID, sahiy_user_id: int, lang: str = "uz_lat"
    ) -> tuple[Optional[int], Optional[ChatReply]]:
        if sahiy_user_id < 1:
            return None, self._reply(_SAHIY_USER_ID_INVALID.get(lang, _SAHIY_USER_ID_INVALID["uz_lat"]))

        if not await self.verify_sahiy_user_id(sahiy_user_id):
            return None, self._reply(_SAHIY_USER_ID_NOT_FOUND.get(lang, _SAHIY_USER_ID_NOT_FOUND["uz_lat"]))

        await self._messages.create(
            session_id=session_id,
            role=MessageRole.USER.value,
            content=f"{SAHIY_USER_MESSAGE_PREFIX}{sahiy_user_id}",
        )
        return sahiy_user_id, None

    async def register_phone_in_session(
        self, session_id: UUID, phone: str, lang: str = "uz_lat"
    ) -> tuple[Optional[int], Optional[ChatReply]]:
        """
        Validate phone, lookup Sahiy user_id, save to session.
        Returns (sahiy_user_id, error_reply) — error_reply set on failure.
        """
        result = await self.verify_phone(phone)
        if result.error == "invalid_format":
            return None, self._reply(invalid_phone_format_text(lang))
        if result.error == "api_unavailable":
            return None, self._reply(api_unavailable_text(lang))
        if result.error == "not_found":
            return None, self._reply(phone_not_registered_text(lang))
        if not result.ok or result.sahiy_user_id is None or not result.phone:
            return None, self._reply(phone_not_registered_text(lang))

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
    def verified_reply(reply_language: str = "uz_lat") -> ChatReply:
        from app.domain.reply_language import localize

        return IdentityService._reply(
            localize("identity_verified_phone", reply_language) or PHONE_VERIFIED_TEXT
        )

    @staticmethod
    def verified_user_id_reply(reply_language: str = "uz_lat") -> ChatReply:
        from app.domain.reply_language import localize

        return IdentityService._reply(
            localize("identity_verified_uid", reply_language) or SAHIY_USER_ID_VERIFIED_TEXT
        )
