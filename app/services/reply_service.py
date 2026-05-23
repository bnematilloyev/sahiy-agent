from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import UUID

from app.core.exceptions import LLMError, LLMTimeoutError
from app.domain.conversation_route import ConversationRoute, RouteDecision
from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import MessageRole, QuestionCategory, ResponseType
from app.domain.scope import is_off_topic, is_operator_request
from app.domain.customer_identity import (
    extract_registration_phone,
    extract_sahiy_user_id,
    is_identity_only_message,
    requires_customer_identity,
)
from app.domain.pickup_keywords import is_identity_registration_text
from app.domain.reply_language import UZ_LAT, localize, resolve_reply_language
from app.handlers.pickup_handler import PickupHandler
from app.domain.category_intent import should_resolve_via_categories
from app.handlers.category_browse_handler import CategoryBrowseHandler
from app.handlers.product_search_handler import ProductSearchHandler
from app.services.product_search_service import ProductSearchService
from app.handlers.routes import IntentRouter
from app.repositories.ports import MessageRepositoryPort
from app.services.conversation_router import ConversationRouterService
from app.services.identity_service import IdentityService
from app.services.intent_service import IntentService

logger = logging.getLogger(__name__)


class ReplyService:
    """Classify intent, run handler, save messages."""

    def __init__(
        self,
        messages: MessageRepositoryPort,
        intent: IntentService,
        router: IntentRouter,
        conversation_router: ConversationRouterService,
        pickup: Optional[PickupHandler] = None,
        product_search: Optional[ProductSearchHandler] = None,
        category_browse: Optional[CategoryBrowseHandler] = None,
    ) -> None:
        self._messages = messages
        self._intent = intent
        self._router = router
        self._conversation_router = conversation_router
        self._pickup = pickup or PickupHandler()
        search_svc = ProductSearchService()
        self._category = category_browse or CategoryBrowseHandler(
            product_search=search_svc
        )
        self._product_search = product_search or ProductSearchHandler(
            service=search_svc,
            category_browse=self._category,
        )
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

        if is_identity_registration_text(text):
            result = self._identity.verified_user_id_reply(reply_lang)
        else:
            decision = await self._conversation_router.decide(chat_context)
            result = await self._dispatch(
                chat_context,
                decision,
                on_stream=stream_callback,
            )

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

    async def _dispatch(
        self,
        chat_context: ChatContext,
        decision: RouteDecision,
        *,
        on_stream: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> ChatReply:
        route = decision.route

        if route == ConversationRoute.CATEGORY:
            return await self._category.reply(chat_context)

        if route == ConversationRoute.PRODUCT_SEARCH:
            meta = dict(chat_context.metadata)
            if decision.search_query:
                meta["product_search_query"] = decision.search_query
            ctx = ChatContext(
                session_id=chat_context.session_id,
                user_id=chat_context.user_id,
                text=chat_context.text,
                channel=chat_context.channel,
                recent_messages=chat_context.recent_messages,
                metadata=meta,
            )
            if should_resolve_via_categories(chat_context.text):
                cat_reply = await self._category.try_resolve_before_product_search(ctx)
                if cat_reply is not None:
                    return cat_reply
            return await self._product_search.reply(ctx)

        if route == ConversationRoute.PICKUP:
            return await self._pickup.reply(chat_context)

        if route == ConversationRoute.API:
            order_handler = self._router.pick(QuestionCategory.API)
            return await order_handler.reply(chat_context)

        if route == ConversationRoute.TICKET:
            support = self._router.pick(QuestionCategory.TICKET)
            if is_operator_request(chat_context.text):
                return await support.reply(
                    chat_context.with_handoff_reason("operator_request")
                )
            return await support.reply(chat_context)

        if route == ConversationRoute.CHITCHAT:
            return await self._reply_faq(
                chat_context,
                recent_messages=[],
                on_stream=on_stream,
            )

        return await self._reply_faq(chat_context, on_stream=on_stream)

    async def _reply_faq(
        self,
        chat_context: ChatContext,
        *,
        recent_messages: Optional[list] = None,
        on_stream: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> ChatReply:
        text = chat_context.text
        reply_lang = str(chat_context.metadata.get("reply_language") or UZ_LAT)
        faq_handler = self._router.pick(QuestionCategory.FAQ)

        if recent_messages is None:
            recent_messages = chat_context.recent_messages

        try:
            if is_operator_request(text):
                support = self._router.pick(QuestionCategory.TICKET)
                return await support.reply(
                    chat_context.with_handoff_reason("operator_request")
                )
            if is_off_topic(text):
                return await faq_handler.reply(chat_context, on_stream=on_stream)
            if on_stream is not None:
                return await faq_handler.reply(chat_context, on_stream=on_stream)
            return await faq_handler.reply(chat_context)
        except (LLMTimeoutError, LLMError) as exc:
            logger.warning("FAQ path failed, retrying static/FAQ: %s", exc)
            try:
                return await faq_handler.reply(chat_context)
            except Exception:
                logger.exception("FAQ fallback failed")
                return ChatReply(
                    response_type=ResponseType.ERROR,
                    text=localize("busy", reply_lang),
                    category=QuestionCategory.FAQ,
                )

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
