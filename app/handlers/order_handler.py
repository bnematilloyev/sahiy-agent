from __future__ import annotations

from app.core.exceptions import LLMError, LLMTimeoutError
from app.core.prompts import API_RESPONSE_SYSTEM
from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import QuestionCategory, ResponseType
from app.infrastructure.order_api import OrderApi
from app.infrastructure.llm.ports import AiClient


class OrderHandler:
    category = QuestionCategory.API

    def __init__(self, order_api: OrderApi, ai: AiClient) -> None:
        self._orders = order_api
        self._ai = ai

    async def reply(self, context: ChatContext) -> ChatReply:
        data = await self._orders.lookup(
            user_id=context.user_id,
            query=context.text,
            session_id=str(context.session_id),
        )
        text = await self._format_reply(data, context.text)
        return ChatReply(
            response_type=ResponseType.API,
            text=text,
            category=self.category,
        )

    async def _format_reply(self, data: dict, query: str) -> str:
        if not self._ai.is_available:
            return self._static_reply(data)

        prompt = (
            f"Customer asked: {query}\n\nAPI data (JSON):\n{data}\n\n"
            "Write a short Uzbek reply with the order status."
        )
        try:
            return await self._ai.complete(API_RESPONSE_SYSTEM, prompt, max_tokens=256)
        except (LLMTimeoutError, LLMError):
            return self._static_reply(data)

    @staticmethod
    def _static_reply(data: dict) -> str:
        order_id = data.get("order_id", "—")
        status = data.get("status_label", data.get("status", "nomalum"))
        eta = data.get("eta", "—")
        return f"{order_id} — {status}, {eta} ichida yetadi."
