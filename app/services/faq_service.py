from __future__ import annotations

import logging
import re
from typing import List, Optional

# --- MUHIM IMPORTLAR ---
from app.repositories.faq_repository import FAQRepository
from app.infrastructure.embeddings.ports import Embedder
from app.infrastructure.llm.ports import AiClient
# -----------------------

from app.core.config import get_settings
from app.core.prompts import (
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

        vector = self._embedder.embed(query)
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

        return await self._faq_repo.search_by_keywords(query)

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
    ) -> str:
        # 1. So'kinishni tekshirish
        if any(word in question.lower() for word in PROFANITY_KEYWORDS):
            return "Iltimos, muloqotda o'zaro hurmatni saqlaylik. Sahiy xizmatiga oid savollaringiz bo'lsa, yordam berishga tayyorman."

        # 2. Agar bazadan (RAG) hech narsa topilmasa
        if not matches:
            static = self.static_answer_for_question(question)
            if static:
                return static
            return NO_FAQ_FALLBACK

        # 3. Salomlashish qo'shish
        greeting = "Assalomu alaykum, hurmatli mijoz! " if self._should_greet(history) else ""

        # 4. AI mavjud bo'lmasa yoki rules mode
        if not self._ai.is_available:
            return greeting + self._compose_local_answer(matches, max_chars=3500)

        # 5. LLM orqali javob
        settings = get_settings()
        context_limit = max(1, settings.rag_top_k)
        context_matches = matches[:context_limit]
        prompt = RAG_USER_TEMPLATE.format(
            context=self._format_matches(context_matches),
            history=self._format_history(history) or "(yo'q)",
            wrapped_question=wrap_user_message(question),
        )

        try:
            ai_reply = await self._ai.complete(
                RAG_SYSTEM,
                prompt,
                max_tokens=settings.rag_max_tokens,
            )
            return f"{greeting}{ai_reply}".strip()
        except Exception as e:
            logger.error(f"RAG LLM failed: {e}")
            return greeting + self._compose_local_answer(
                matches, max_chars=3500
            )

    @staticmethod
    def _compose_local_answer(
        matches: List[FAQEntry],
        *,
        max_chars: int = 3500,
    ) -> str:
        """AI yo'q bo'lsa — FAQ javoblarini to'liq (qisqartirmasdan) berish."""
        parts: List[str] = []
        for entry in matches:
            block = entry.answer.strip()
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
    def _format_matches(entries: List[FAQEntry]) -> str:
        return "\n\n".join(
            f"Q: {e.question}\nA: {e.answer}"
            for e in entries
        )

    @staticmethod
    def _format_history(messages: List[Message]) -> str:
        lines = []
        for message in messages[-6:]:
            role = "Mijoz" if message.role == MessageRole.USER.value else "Yordamchi"
            lines.append(f"{role}: {message.content}")
        return "\n".join(lines)