from __future__ import annotations

import logging
import re
from typing import Awaitable, Callable, List, Optional

# --- MUHIM IMPORTLAR ---
from app.repositories.faq_repository import FAQRepository
from app.infrastructure.embeddings.ports import Embedder
from app.infrastructure.llm.ports import AiClient
# -----------------------

from app.core.config import get_settings
from app.core.prompts import (
    GENERIC_ASSISTANT_SYSTEM,
    GENERIC_ASSISTANT_USER_TEMPLATE,
    NO_FAQ_FALLBACK,
    PROFANITY_KEYWORDS,
    RAG_SYSTEM,
    RAG_USER_TEMPLATE,
    SAHIY_COMPANY_ANSWER,
    wrap_user_message,
)
from app.domain.entities import FAQEntry, Message
from app.domain.enums import MessageRole
from app.domain.classification import is_company_question
from app.domain.faq_locale import faq_entry_for_language
from app.domain.reply_language import UZ_LAT, localize, system_prompt_with_language
from app.domain.text_normalize import normalize_text

logger = logging.getLogger(__name__)


class FaqService:
    """Search FAQ vectors and compose an answer."""

    def __init__(
            self,
            faq_repo: FAQRepository,
            embedder: Embedder,
            ai: AiClient
    ) -> None:
        self._faq_repo = faq_repo
        self._embedder = embedder
        self._ai = ai

    async def find_matches(self, query: str) -> List[FAQEntry]:
        settings = get_settings()
        threshold: Optional[float] = None
        if settings.resolved_embedding_provider() == "mock":
            threshold = 0.55

        normalized_query = normalize_text(query)
        search_text = normalized_query if normalized_query else query

        vector = self._embedder.embed(search_text)
        matches = await self._faq_repo.search_similar(embedding=vector, threshold=threshold)

        if matches:
            ranked = sorted(matches, key=lambda entry: entry.similarity, reverse=True)
            min_score = threshold if threshold is not None else settings.rag_similarity_threshold
            if ranked[0].similarity < min_score:
                logger.info(
                    "Low vector similarity: %s < %s",
                    ranked[0].similarity,
                    min_score,
                )
                return []
            return ranked

        return await self._faq_repo.search_by_keywords(search_text)

    def _should_greet(self, history: List[Message]) -> bool:
        """Tarixda botning biror xabari borligini tekshiradi."""
        return not any(m.role == MessageRole.ASSISTANT.value for m in history)

    def static_answer_for_question(self, question: str) -> Optional[str]:
        if is_company_question(question):
            return SAHIY_COMPANY_ANSWER
        return None

    async def answer(
            self,
            question: str,
            matches: List[FAQEntry],
            history: List[Message],
            *,
            reply_language: str = UZ_LAT,
            on_stream: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        # 1. So'kinishni tekshirish
        if any(word in question.lower() for word in PROFANITY_KEYWORDS):
            return "Iltimos, muloqotda o'zaro hurmatni saqlaylik. Sahiy xizmatiga oid savollaringiz bo'lsa, yordam berishga tayyorman."

        # 2. Agar bazadan (RAG) hech narsa topilmasa — generic AI yordamchisi
        if not matches:
            static = self.static_answer_for_question(question)
            if static:
                if on_stream is not None:
                    await on_stream(static)
                return static
            return await self.generic_ai_answer(
                question=question,
                history=history,
                reply_language=reply_language,
                on_stream=on_stream,
            )

        # 3. Salomlashish qo'shish
        greeting = (
            localize("rag_greeting", reply_language) if self._should_greet(history) else ""
        )

        # 4. AI mavjud bo'lmasa yoki rules mode
        if not self._ai.is_available:
            text = greeting + self._compose_local_answer(
                matches, max_chars=3500, reply_language=reply_language
            )
            if on_stream is not None:
                await on_stream(text)
            return text

        # 5. LLM orqali javob
        settings = get_settings()
        context_limit = max(1, settings.rag_top_k)
        context_matches = matches[:context_limit]
        prompt = RAG_USER_TEMPLATE.format(
            context=self._format_matches(context_matches, reply_language),
            history=self._format_history(history) or "(yo'q)",
            wrapped_question=wrap_user_message(question),
        )
        system = system_prompt_with_language(RAG_SYSTEM, reply_language)

        try:
            accumulated = greeting
            if on_stream is not None and accumulated:
                await on_stream(accumulated)
            async for token in self._ai.complete_stream(
                system,
                prompt,
                max_tokens=settings.rag_max_tokens,
            ):
                accumulated += token
                if on_stream is not None:
                    await on_stream(accumulated)
            return accumulated.strip()
        except Exception as e:
            logger.error(f"RAG LLM failed: {e}")
            text = greeting + self._compose_local_answer(
                matches, max_chars=3500, reply_language=reply_language
            )
            if on_stream is not None:
                await on_stream(text)
            return text

    async def generic_ai_answer(
        self,
        *,
        question: str,
        history: List[Message],
        reply_language: str = UZ_LAT,
        on_stream: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        """FAQ topilmagan paytda Sahiy doirasida xushmuomilali AI javob."""
        if any(word in question.lower() for word in PROFANITY_KEYWORDS):
            text = (
                "Iltimos, muloqotda o'zaro hurmatni saqlaylik. "
                "Sahiy xizmatiga oid savollaringiz bo'lsa, yordam berishga tayyorman."
            )
            if on_stream is not None:
                await on_stream(text)
            return text

        if not self._ai.is_available:
            text = localize("no_faq_fallback", reply_language)
            if on_stream is not None:
                await on_stream(text)
            return text

        settings = get_settings()
        prompt = GENERIC_ASSISTANT_USER_TEMPLATE.format(
            history=self._format_history(history) or "(yo'q)",
            wrapped_question=wrap_user_message(question),
        )
        system = system_prompt_with_language(
            GENERIC_ASSISTANT_SYSTEM, reply_language
        )
        try:
            accumulated = ""
            async for token in self._ai.complete_stream(
                system,
                prompt,
                max_tokens=settings.rag_max_tokens,
            ):
                accumulated += token
                if on_stream is not None:
                    await on_stream(accumulated)
            text = accumulated.strip()
            return text or localize("no_faq_fallback", reply_language)
        except Exception as exc:
            logger.warning("generic_ai_answer failed: %s", exc)
            text = localize("no_faq_fallback", reply_language)
            if on_stream is not None:
                await on_stream(text)
            return text

    @staticmethod
    def _compose_local_answer(
        matches: List[FAQEntry],
        *,
        max_chars: int = 3500,
        reply_language: str = UZ_LAT,
    ) -> str:
        """AI yo'q bo'lsa — FAQ javoblarini to'liq (qisqartirmasdan) berish."""
        parts: List[str] = []
        for entry in matches:
            localized = faq_entry_for_language(entry, reply_language)
            block = localized.answer.strip()
            if block and block not in parts:
                parts.append(block)
        text = "\n\n".join(parts).strip()
        if len(text) <= max_chars:
            return text
        trimmed = text[:max_chars].rsplit("\n", 1)[0].strip()
        if trimmed and trimmed[-1] not in ".!?":
            trimmed += "..."
        return trimmed

    @staticmethod
    def _format_matches(entries: List[FAQEntry], reply_language: str) -> str:
        return "\n\n".join(
            f"Q: {faq_entry_for_language(e, reply_language).question}\n"
            f"A: {faq_entry_for_language(e, reply_language).answer}"
            for e in entries
        )

    @staticmethod
    def _format_history(messages: List[Message]) -> str:
        lines = []
        for message in messages[-6:]:
            role = "Mijoz" if message.role == MessageRole.USER.value else "Yordamchi"
            lines.append(f"{role}: {message.content}")
        return "\n".join(lines)