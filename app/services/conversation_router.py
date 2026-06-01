"""LLM-first conversation routing with session context (Anthropic/OpenAI chain)."""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from app.core.prompts import ROUTER_SYSTEM, ROUTER_USER_TEMPLATE, wrap_user_message
from app.core.exceptions import LLMError, LLMTimeoutError
from app.domain.category_intent import is_category_browse_intent
from app.domain.conversation_route import ConversationRoute, RouteDecision
from app.domain.conversation_thread import format_thread_hint_for_router
from app.domain.dto import ChatContext
from app.domain.entities import Message
from app.domain.enums import MessageRole, QuestionCategory
from app.domain.keywords import classify_by_keywords, is_chitchat
from app.domain.order_refs import extract_track, is_order_lookup_request
from app.domain.pickup_keywords import is_pickup_conversation_turn
from app.domain.product_search_intent import is_product_search_intent
from app.domain.scope import is_operator_request
from app.infrastructure.llm.ports import AiClient
from app.domain.reply_language import _ALL_LANGS

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

        # Track raqami aniq — buyurtma API
        if extract_track(text):
            return RouteDecision(route=ConversationRoute.API)

        # LLM birinchi: tarix + mavzu almashishi (Anthropic/OpenAI)
        if self._ai.is_available:
            llm_decision = await self._decide_with_llm(context)
            if llm_decision is not None:
                reconciled = _reconcile_llm_with_signals(text, context.recent_messages, llm_decision)
                return reconciled

        return self._fallback(context)

    async def _decide_with_llm(self, context: ChatContext) -> Optional[RouteDecision]:
        history = self._format_history(context.recent_messages)
        thread_hint = format_thread_hint_for_router(context.recent_messages)
        preferred = context.metadata.get("reply_language")
        # Menuda tanlangan til — LLMga ma'lumot sifatida uzatamiz.
        # LLM joriy xabar tiliga qarab to'g'rilab qaytara oladi.
        lang_hint = (
            f"Mijoz menuda tanlagan til: {preferred}. "
            "Joriy xabar boshqa tilda yozilgan bo'lsa, o'sha tilni reply_language sifatida qaytaring.\n"
        ) if preferred in _ALL_LANGS else ""
        wrapped = wrap_user_message(context.text, max_len=1500)
        user_prompt = ROUTER_USER_TEMPLATE.format(
            thread_hint=thread_hint,
            history=history or "(yo'q)",
            wrapped=wrapped,
        )
        if lang_hint:
            user_prompt = lang_hint + user_prompt
        try:
            raw = await self._ai.complete(ROUTER_SYSTEM, user_prompt, max_tokens=160)
        except (LLMTimeoutError, LLMError) as exc:
            logger.warning("Conversation router LLM failed: %s", exc)
            return None

        parsed = _parse_router_json(raw)
        if parsed is None:
            logger.warning("Conversation router parse failed, raw=%r", raw[:200])
            return None

        logger.info(
            "conversation route=%s search_query=%r reply_language=%s text=%r",
            parsed.route.value,
            (parsed.search_query or "")[:60],
            parsed.reply_language,
            context.text[:60],
        )
        return parsed

    @staticmethod
    def _format_history(messages: List[Message]) -> str:
        lines: list[str] = []
        for message in messages[-10:]:
            role = "Mijoz" if message.role == MessageRole.USER.value else "Yordamchi"
            content = (message.content or "").strip()
            if content:
                snippet = content[:600]
                if message.role == MessageRole.ASSISTANT.value:
                    from app.domain.conversation_thread import infer_topic_from_assistant_text

                    topic = infer_topic_from_assistant_text(content)
                    if topic:
                        snippet = f"[{topic}] {snippet}"
                lines.append(f"{role}: {snippet}")
        return "\n".join(lines)

    def _fallback(self, context: ChatContext) -> RouteDecision:
        text = context.text
        if is_category_browse_intent(text):
            return RouteDecision(route=ConversationRoute.CATEGORY)
        if is_pickup_conversation_turn(text, context.recent_messages):
            return RouteDecision(route=ConversationRoute.PICKUP)
        if is_product_search_intent(text):
            return RouteDecision(
                route=ConversationRoute.PRODUCT_SEARCH,
                search_query=text.strip(),
            )
        if is_order_lookup_request(text):
            return RouteDecision(route=ConversationRoute.API)
        if is_chitchat(text):
            return RouteDecision(route=ConversationRoute.CHITCHAT)

        label = classify_by_keywords(text)
        if label == QuestionCategory.API.value:
            return RouteDecision(route=ConversationRoute.API)
        if label == QuestionCategory.TICKET.value:
            return RouteDecision(route=ConversationRoute.TICKET)
        return RouteDecision(route=ConversationRoute.FAQ)


def _reconcile_llm_with_signals(
    text: str,
    recent_messages: List[Message],
    decision: RouteDecision,
) -> RouteDecision:
    """LLM xato qolgan aniq holatlar: kuchli keyword signal > pickup thread inertia.

    Eslatma: barcha yangi RouteDecision'larda decision.reply_language saqlanadi —
    aks holda LLM tomonidan aniqlangan til yo'qoladi.
    """
    lang = decision.reply_language
    route = decision.route

    if route == ConversationRoute.PICKUP and is_category_browse_intent(text):
        logger.info("router reconcile: pickup -> category (category intent)")
        return RouteDecision(route=ConversationRoute.CATEGORY, reply_language=lang)

    if route == ConversationRoute.PICKUP and is_product_search_intent(text):
        if not is_pickup_conversation_turn(text, recent_messages):
            logger.info("router reconcile: pickup -> product_search")
            return RouteDecision(
                route=ConversationRoute.PRODUCT_SEARCH,
                search_query=decision.search_query or text.strip(),
                reply_language=lang,
            )

    if route == ConversationRoute.PRODUCT_SEARCH and is_category_browse_intent(text):
        logger.info("router reconcile: product_search -> category")
        return RouteDecision(route=ConversationRoute.CATEGORY, reply_language=lang)

    if route == ConversationRoute.CATEGORY and extract_track(text):
        return RouteDecision(route=ConversationRoute.API, reply_language=lang)

    return decision


def _parse_router_json(raw: str) -> Optional[RouteDecision]:
    body = raw.strip()
    if "```" in body:
        match = re.search(r"\{.*\}", body, re.DOTALL)
        if match:
            body = match.group(0)
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
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
    reply_language = str(data.get("reply_language") or "").strip() or None
    if reply_language not in _ALL_LANGS:
        reply_language = None
    return RouteDecision(
        route=ConversationRoute(route_raw),
        search_query=search_query,
        reply_language=reply_language,
    )


def is_identity_only_fast_path(text: str) -> bool:
    from app.domain.customer_identity import is_identity_only_message
    from app.domain.pickup_keywords import is_identity_registration_text

    return is_identity_registration_text(text) or is_identity_only_message(text)
