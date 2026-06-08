from __future__ import annotations

from typing import Awaitable, Callable, Optional

from app.core.prompts import BROKEN_GOODS_POLICY_ANSWER
from app.domain.reply_language import UZ_LAT, localize
from app.domain.classification import is_broken_goods_policy_question, is_company_question
from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import QuestionCategory, ResponseType
from app.handlers.support_handler import SupportHandler
from app.services.faq_service import FaqService

# Confidence threshold below which the reply is considered "uncertain".
# The Go orchestrator compares its own threshold against this value.
_LOW_CONFIDENCE: float = 0.3


class FaqHandler:
    category = QuestionCategory.FAQ

    def __init__(self, faq: FaqService, support: SupportHandler) -> None:
        self._faq = faq
        self._support = support

    async def reply(
        self,
        context: ChatContext,
        *,
        on_stream: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> ChatReply:
        lang = str(context.metadata.get("reply_language") or UZ_LAT)

        # Static / rule-based answers carry full confidence (no LLM uncertainty).
        if is_broken_goods_policy_question(context.text):
            return ChatReply(
                response_type=ResponseType.AUTO,
                text=BROKEN_GOODS_POLICY_ANSWER,
                category=self.category,
                confidence=1.0,
            )

        if is_company_question(context.text):
            company = self._faq.static_answer_for_question(context.text)
            if company:
                return ChatReply(
                    response_type=ResponseType.AUTO,
                    text=company,
                    category=self.category,
                    confidence=1.0,
                )

        matches = await self._faq.find_matches(context.text)
        if not matches:
            # No FAQ match — the AI will attempt a generic answer but it is
            # uncertain. Go may still show the reply; it decides whether to
            # escalate based on its own threshold.
            static = self._faq.static_answer_for_question(context.text)
            if static:
                if on_stream is not None:
                    await on_stream(static)
                return ChatReply(
                    response_type=ResponseType.AUTO,
                    text=static,
                    category=self.category,
                    confidence=1.0,
                )
            text = await self._faq.generic_ai_answer(
                question=context.text,
                history=context.recent_messages,
                reply_language=lang,
                on_stream=on_stream,
            )
            return ChatReply(
                response_type=ResponseType.AUTO,
                text=text,
                category=self.category,
                # Low confidence: no vector match; reply is a best-effort guess.
                confidence=_LOW_CONFIDENCE,
            )

        # Best match similarity becomes the confidence score.
        best_similarity = matches[0].similarity if hasattr(matches[0], "similarity") else 0.7
        answer = await self._faq.answer(
            question=context.text,
            matches=matches,
            history=context.recent_messages,
            reply_language=lang,
            on_stream=on_stream,
        )
        return ChatReply(
            response_type=ResponseType.AUTO,
            text=answer,
            category=self.category,
            confidence=min(1.0, max(0.0, float(best_similarity))),
        )
