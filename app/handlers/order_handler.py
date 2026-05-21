from __future__ import annotations

import json

from app.core.exceptions import LLMError, LLMTimeoutError
from app.core.prompts import API_ORDER_USER_TEMPLATE, API_RESPONSE_SYSTEM
from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import QuestionCategory, ResponseType
from app.domain.order_present import format_orders_message, summarize_orders_for_prompt
from app.domain.order_refs import build_order_query_text, extract_track
from app.domain.verified_phone import sahiy_user_id_from_context, verified_phone_from_context
from app.infrastructure.llm.ports import AiClient
from app.infrastructure.order_api import OrderApi


class OrderHandler:
    category = QuestionCategory.API

    def __init__(self, order_api: OrderApi, ai: AiClient) -> None:
        self._orders = order_api
        self._ai = ai

    async def reply(self, context: ChatContext) -> ChatReply:
        phone = verified_phone_from_context(context)
        sahiy_uid = sahiy_user_id_from_context(context)

        query = build_order_query_text(context.text, context.recent_messages)
        data = await self._orders.lookup(
            user_id=context.user_id,
            query=query,
            session_id=str(context.session_id),
            phone=phone,
            sahiy_user_id=sahiy_uid,
        )
        track = extract_track(query)
        if track and isinstance(data, dict):
            data["requested_track"] = track
        text = await self._format_reply(data, query)
        return ChatReply(
            response_type=ResponseType.API,
            text=text,
            category=self.category,
        )

    async def _format_reply(self, data: dict, query: str) -> str:
        summary = summarize_orders_for_prompt(data)
        if data.get("error") or data.get("ownership_mismatch"):
            return format_orders_message(data)

        # Ro'yxat javoblarini barqaror formatda berish (LLM qisqartirmasin / Jiyun demasin)
        if summary.get("bolimlar"):
            return format_orders_message(data)

        if not self._ai.is_available:
            return format_orders_message(data)

        prompt = API_ORDER_USER_TEMPLATE.format(
            query=query,
            orders_json=json.dumps(summary, ensure_ascii=False, indent=2),
        )
        try:
            return await self._ai.complete(API_RESPONSE_SYSTEM, prompt, max_tokens=768)
        except (LLMTimeoutError, LLMError):
            return format_orders_message(data)
