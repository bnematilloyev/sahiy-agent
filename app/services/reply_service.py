from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from app.core.exceptions import LLMError, LLMTimeoutError
from app.core.prompts import BUSY_MESSAGE, CHITCHAT_REPLY
from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import MessageRole, QuestionCategory, ResponseType
from app.domain.keywords import is_chitchat
from app.domain.scope import is_off_topic, is_operator_request
from app.handlers.routes import IntentRouter
from app.repositories.message_repository import MessageRepository
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

    async def reply(
        self,
        session_id: UUID,
        user_id: str,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ChatReply:
        meta = context or {}
        channel = str(meta.get("channel", "telegram"))

        recent = await self._messages.get_recent(session_id, limit=10)
        chat_context = ChatContext(
            session_id=session_id,
            user_id=user_id,
            text=text,
            channel=channel,
            recent_messages=recent,
            metadata=meta,
        )

        await self._messages.create(
            session_id=session_id,
            role=MessageRole.USER.value,
            content=text,
        )

        if is_chitchat(text):
            result = ChatReply(
                response_type=ResponseType.AUTO,
                text=CHITCHAT_REPLY,
                category=QuestionCategory.FAQ,
            )
            await self._messages.create(
                session_id=session_id,
                role=MessageRole.ASSISTANT.value,
                content=result.text,
                msg_type=result.response_type.value,
            )
            return result

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
                result = await handler.reply(chat_context)
        except (LLMTimeoutError, LLMError) as exc:
            logger.warning("AI unavailable, trying FAQ handler: %s", exc)
            try:
                faq_handler = self._router.pick(QuestionCategory.FAQ)
                result = await faq_handler.reply(chat_context)
            except Exception:
                logger.exception("FAQ fallback failed")
                result = ChatReply(
                    response_type=ResponseType.ERROR,
                    text=BUSY_MESSAGE,
                    category=QuestionCategory.FAQ,
                )

        if not result.text.strip():
            result = ChatReply(
                response_type=ResponseType.ERROR,
                text=BUSY_MESSAGE,
                category=result.category,
                ticket_id=result.ticket_id,
            )

        await self._messages.create(
            session_id=session_id,
            role=MessageRole.ASSISTANT.value,
            content=result.text,
            msg_type=result.response_type.value,
        )
        return result
