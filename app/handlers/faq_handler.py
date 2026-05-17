from __future__ import annotations

from app.core.prompts import NO_FAQ_FALLBACK
from app.domain.classification import is_company_question
from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import QuestionCategory, ResponseType
from app.handlers.support_handler import SupportHandler
from app.services.faq_service import FaqService


class FaqHandler:
    category = QuestionCategory.FAQ

    def __init__(self, faq: FaqService, support: SupportHandler) -> None:
        self._faq = faq
        self._support = support

    async def reply(self, context: ChatContext) -> ChatReply:
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
            text = self._faq.static_answer_for_question(context.text) or NO_FAQ_FALLBACK
            return ChatReply(
                response_type=ResponseType.AUTO,
                text=text,
                category=self.category,
            )

        answer = await self._faq.answer(
            question=context.text,
            matches=matches,
            history=context.recent_messages,
        )
        return ChatReply(
            response_type=ResponseType.AUTO,
            text=answer,
            category=self.category,
        )
