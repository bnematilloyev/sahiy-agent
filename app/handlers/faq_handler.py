from __future__ import annotations

from typing import Awaitable, Callable, Optional

from app.core.prompts import BROKEN_GOODS_POLICY_ANSWER
from app.domain.reply_language import UZ_LAT, localize
from app.domain.classification import is_broken_goods_policy_question, is_company_question
from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import QuestionCategory, ResponseType
from app.handlers.support_handler import SupportHandler
from app.services.faq_service import FaqService


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

        if is_broken_goods_policy_question(context.text):
            return ChatReply(
                response_type=ResponseType.AUTO,
                text=BROKEN_GOODS_POLICY_ANSWER,
                category=self.category,
            )

        if is_company_question(context.text):
            company = self._faq.static_answer_for_question(context.text)
            if company:
                return ChatReply(
                    response_type=ResponseType.AUTO,
                    text=company,
                    category=self.category,
                )

        matches = await self._faq.find_matches(context.text)
        if not matches:
            text = (
                self._faq.static_answer_for_question(context.text)
                or localize("no_faq_fallback", lang)
            )
            return ChatReply(
                response_type=ResponseType.AUTO,
                text=text,
                category=self.category,
            )

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
        )
