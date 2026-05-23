"""LLM-first conversation routing with session context (Anthropic/OpenAI chain)."""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from app.core.prompts import ROUTER_SYSTEM, ROUTER_USER_TEMPLATE, wrap_user_message
from app.core.exceptions import LLMError, LLMTimeoutError
from app.domain.conversation_route import ConversationRoute, RouteDecision
from app.domain.dto import ChatContext
from app.domain.entities import Message
from app.domain.enums import MessageRole, QuestionCategory
from app.domain.keywords import classify_by_keywords, is_chitchat
from app.domain.order_refs import extract_track, is_order_lookup_request
from app.domain.pickup_keywords import is_pickup_conversation_turn
from app.domain.category_intent import is_category_browse_intent
from app.domain.product_search_intent import is_product_search_intent
from app.domain.scope import is_operator_request
from app.infrastructure.llm.ports import AiClient

logger = logging.getLogger(__name__)

_VALID_ROUTES = {r.value for r in ConversationRoute}


class ConversationRouterService:
    """Pick backend path (FAQ, orders API, product search, …) using LLM + fallbacks."""

    def __init__(self, ai: AiClient) -> None:
        self._ai = ai

    async def decide(self, context: ChatContext) -> RouteDecision:
        text = (context.text or "").strip()
        if not text:
            return RouteDecision(route=ConversationRoute.FAQ)

        if is_identity_only_fast_path(text):
            return RouteDecision(route=ConversationRoute.FAQ)

        if is_operator_request(text):
            return RouteDecision(route=ConversationRoute.TICKET)

        # Track raqami aniq bo'lsa — LLM sarflamasdan to'g'ridan-to'g'ri API
        if extract_track(text):
            return RouteDecision(route=ConversationRoute.API)

        if is_pickup_conversation_turn(text, context.recent_messages):
            return RouteDecision(route=ConversationRoute.PICKUP)

        if is_category_browse_intent(text):
            return RouteDecision(route=ConversationRoute.CATEGORY)

        # Mahsulot qidiruv sигнали bo'lsa — LLM ishlatib, kontekstdan
        # foydalanib aniqlaymiz (order lookup bilan kolliziya bo'lishi mumkin)
        if self._ai.is_available:
            llm_decision = await self._decide_with_llm(context)
            if llm_decision is not None:
                return llm_decision

        # LLM yo'q yoki xato — heuristikaga qayt
        if is_order_lookup_request(text):
            return RouteDecision(route=ConversationRoute.API)

        return self._fallback(context)

    async def _decide_with_llm(self, context: ChatContext) -> Optional[RouteDecision]:
        history = self._format_history(context.recent_messages)
        wrapped = wrap_user_message(context.text, max_len=1500)
        user_prompt = ROUTER_USER_TEMPLATE.format(history=history or "(yo'q)", wrapped=wrapped)
        try:
            raw = await self._ai.complete(ROUTER_SYSTEM, user_prompt, max_tokens=120)
        except (LLMTimeoutError, LLMError) as exc:
            logger.warning("Conversation router LLM failed: %s", exc)
            return None

        parsed = _parse_router_json(raw)
        if parsed is None:
            logger.warning("Conversation router parse failed, raw=%r", raw[:200])
            return None

        logger.info(
            "conversation route=%s search_query=%r text=%r",
            parsed.route.value,
            (parsed.search_query or "")[:60],
            context.text[:60],
        )
        return parsed

    @staticmethod
    def _format_history(messages: List[Message]) -> str:
        lines: list[str] = []
        for message in messages[-8:]:
            role = "Mijoz" if message.role == MessageRole.USER.value else "Yordamchi"
            content = (message.content or "").strip()
            if content:
                lines.append(f"{role}: {content[:500]}")
        return "\n".join(lines)

    def _fallback(self, context: ChatContext) -> RouteDecision:
        text = context.text
        if is_pickup_conversation_turn(text, context.recent_messages):
            return RouteDecision(route=ConversationRoute.PICKUP)
        if is_category_browse_intent(text):
            return RouteDecision(route=ConversationRoute.CATEGORY)
        if is_product_search_intent(text):
            return RouteDecision(
                route=ConversationRoute.PRODUCT_SEARCH,
                search_query=text.strip(),
            )
        if is_chitchat(text):
            return RouteDecision(route=ConversationRoute.CHITCHAT)

        label = classify_by_keywords(text)
        if label == QuestionCategory.API.value:
            return RouteDecision(route=ConversationRoute.API)
        if label == QuestionCategory.TICKET.value:
            return RouteDecision(route=ConversationRoute.TICKET)
        return RouteDecision(route=ConversationRoute.FAQ)


def _parse_router_json(raw: str) -> Optional[RouteDecision]:
    body = raw.strip()
    if "```" in body:
        match = re.search(r"\{[^{}]*\}", body, re.DOTALL)
        if match:
            body = match.group(0)
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        # Ba'zan model faqat "product_search" yozadi
        token = body.lower().split()[0] if body else ""
        if token in _VALID_ROUTES:
            return RouteDecision(route=ConversationRoute(token))
        return None

    if not isinstance(data, dict):
        return None

    route_raw = str(data.get("route") or "").strip().lower()
    if route_raw not in _VALID_ROUTES:
        return None

    search_query = str(data.get("search_query") or "").strip() or None
    return RouteDecision(
        route=ConversationRoute(route_raw),
        search_query=search_query,
    )


def is_identity_only_fast_path(text: str) -> bool:
    from app.domain.customer_identity import is_identity_only_message
    from app.domain.pickup_keywords import is_identity_registration_text

    return is_identity_registration_text(text) or is_identity_only_message(text)
