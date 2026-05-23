from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import UUID

from app.core.exceptions import LLMError, LLMTimeoutError
from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import MessageRole, QuestionCategory, ResponseType
from app.domain.keywords import is_chitchat
from app.domain.scope import is_off_topic, is_operator_request
from app.domain.customer_identity import (
    extract_registration_phone,
    extract_sahiy_user_id,
    is_identity_only_message,
    requires_customer_identity,
)
from app.domain.pickup_keywords import is_identity_registration_text
from app.domain.reply_language import UZ_LAT, localize, resolve_reply_language
from app.domain.order_refs import is_order_lookup_request
from app.domain.pickup_keywords import (
    is_pickup_conversation_turn,
    is_support_or_order_topic,
)
from app.handlers.pickup_handler import PickupHandler
from app.handlers.routes import IntentRouter
from app.repositories.message_repository import MessageRepository
from app.services.identity_service import IdentityService
from app.services.intent_service import IntentService

logger = logging.getLogger(__name__)


class ReplyService:
    """Classify intent, run handler, save messages."""

    def __init__(
        self,
        messages: MessageRepository,
        intent: IntentService,
        router: IntentRouter,
    ) -> None:
        self._messages = messages
        self._intent = intent
        self._router = router
        self._pickup = PickupHandler()
        self._identity = IdentityService(messages)

    async def reply(
        self,
        session_id: UUID,
        user_id: str,
        text: str,
        context: Optional[Dict[str, Any]] = None,
        *,
        on_stream: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> ChatReply:
        meta = dict(context or {})
        channel = str(meta.get("channel", "telegram"))
        streamed = False
        stream_callback = on_stream
        if stream_callback is not None:
            _original_stream = stream_callback

            async def stream_callback(chunk: str) -> None:
                nonlocal streamed
                streamed = True
                await _original_stream(chunk)

        stored_phone, stored_uid = await self._messages.find_customer_identity(session_id)
        if stored_phone and not meta.get("verified_phone"):
            meta["verified_phone"] = stored_phone
        if stored_uid is not None and meta.get("sahiy_user_id") is None:
            meta["sahiy_user_id"] = stored_uid

        recent = await self._messages.get_recent(session_id, limit=10)

        reply_lang = resolve_reply_language(text, meta, recent)
        meta["reply_language"] = reply_lang

        await self._messages.create(
            session_id=session_id,
            role=MessageRole.USER.value,
            content=text,
        )

        if requires_customer_identity(channel):
            identity_reply = await self._ensure_verified_customer(
                session_id=session_id,
                meta=meta,
                text=text,
            )
            if identity_reply is not None:
                await self._messages.create(
                    session_id=session_id,
                    role=MessageRole.ASSISTANT.value,
                    content=identity_reply.text,
                    msg_type=identity_reply.response_type.value,
                )
                if stream_callback is not None:
                    await stream_callback(identity_reply.text)
                return identity_reply
            chat_context = ChatContext(
                session_id=session_id,
                user_id=user_id,
                text=text,
                channel=channel,
                recent_messages=recent,
                metadata=meta,
            )
        else:
            chat_context = ChatContext(
                session_id=session_id,
                user_id=user_id,
                text=text,
                channel=channel,
                recent_messages=recent,
                metadata=meta,
            )

        if is_identity_registration_text(text):
            result = self._identity.verified_user_id_reply(reply_lang)
        elif is_order_lookup_request(text):
            order_handler = self._router.pick(QuestionCategory.API)
            result = await order_handler.reply(chat_context)
        elif is_support_or_order_topic(text):
            result = await self._route_intent(chat_context, text)
        elif is_pickup_conversation_turn(text, recent):
            result = await self._pickup.reply(chat_context)
        elif is_chitchat(text):
            result = ChatReply(
                response_type=ResponseType.AUTO,
                text=localize("chitchat", reply_lang),
                category=QuestionCategory.FAQ,
            )
        else:
            result = await self._route_intent(chat_context, text, on_stream=stream_callback)

        if not result.text.strip():
            result = ChatReply(
                response_type=ResponseType.ERROR,
                text=localize("busy", reply_lang),
                category=result.category,
                ticket_id=result.ticket_id,
            )

        await self._messages.create(
            session_id=session_id,
            role=MessageRole.ASSISTANT.value,
            content=result.text,
            msg_type=result.response_type.value,
        )
        if stream_callback is not None and not streamed:
            await stream_callback(result.text)
        return result

    async def _ensure_verified_customer(
        self,
        *,
        session_id: UUID,
        meta: Dict[str, Any],
        text: str,
    ) -> Optional[ChatReply]:
        """Block until Sahiy user_id is known; accept Sahiy ID or phone in text."""
        if meta.get("sahiy_user_id") is not None:
            return None

        _rlang = meta.get("reply_language", "uz_lat")
        sahiy_id_in_text = extract_sahiy_user_id(text)
        if sahiy_id_in_text is not None:
            sahiy_uid, err = await self._identity.register_sahiy_user_id_in_session(
                session_id, sahiy_id_in_text, lang=_rlang
            )
            if err is not None:
                return err
            meta["sahiy_user_id"] = sahiy_uid
            if is_identity_only_message(text):
                return self._identity.verified_user_id_reply(_rlang)
            return None

        phone_in_text = extract_registration_phone(text)
        if phone_in_text:
            sahiy_uid, err = await self._identity.register_phone_in_session(
                session_id, phone_in_text, lang=_rlang
            )
            if err is not None:
                return err
            meta["verified_phone"] = phone_in_text
            meta["sahiy_user_id"] = sahiy_uid
            if is_identity_only_message(text):
                return self._identity.verified_reply(_rlang)
            return None

        from app.domain.customer_identity import identity_required_text
        lang = resolve_reply_language(text, meta, None)
        return ChatReply(
            response_type=ResponseType.AUTO,
            text=identity_required_text(lang),
            category=QuestionCategory.FAQ,
        )

    async def _route_intent(
        self,
        chat_context: ChatContext,
        text: str,
        *,
        on_stream: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> ChatReply:
        try:
            if is_off_topic(text):
                support = self._router.pick(QuestionCategory.TICKET)
                result = await support.reply(chat_context.with_handoff_reason("off_topic"))
            elif is_operator_request(text):
                support = self._router.pick(QuestionCategory.TICKET)
                result = await support.reply(
                    chat_context.with_handoff_reason("operator_request")
                )
            else:
                category = await self._intent.detect(text)
                handler = self._router.pick(category)
                if category == QuestionCategory.FAQ and on_stream is not None:
                    result = await handler.reply(chat_context, on_stream=on_stream)
                else:
                    result = await handler.reply(chat_context)
        except (LLMTimeoutError, LLMError) as exc:
            logger.warning("AI unavailable, trying FAQ handler: %s", exc)
            try:
                faq_handler = self._router.pick(QuestionCategory.FAQ)
                result = await faq_handler.reply(chat_context)
            except Exception:
                logger.exception("FAQ fallback failed")
                lang = chat_context.metadata.get("reply_language", UZ_LAT)
                result = ChatReply(
                    response_type=ResponseType.ERROR,
                    text=localize("busy", lang),
                    category=QuestionCategory.FAQ,
                )
        return result
