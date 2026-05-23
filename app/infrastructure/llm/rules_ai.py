from __future__ import annotations

import re
from collections.abc import AsyncIterator

from app.core.prompts import CLASSIFIER_MARKER, NO_FAQ_FALLBACK, RAG_SYSTEM, extract_user_message
from app.domain.keywords import classify_by_keywords


class RulesAi:
    """Simple rule-based AI when OPENAI_API_KEY is not set."""

    @property
    def is_available(self) -> bool:
        return False

    async def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
        if CLASSIFIER_MARKER in system_prompt:
            text = extract_user_message(user_prompt)
            return classify_by_keywords(text)
        if system_prompt == RAG_SYSTEM or "FAQ kontekst" in user_prompt:
            return self._answer_from_faq(user_prompt)
        return NO_FAQ_FALLBACK

    async def complete_stream(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 1024
    ) -> AsyncIterator[str]:
        yield await self.complete(system_prompt, user_prompt, max_tokens=max_tokens)

    @staticmethod
    def _answer_from_faq(user_prompt: str) -> str:
        blocks = re.findall(
            r"Q:\s*(?P<q>.+?)\nA:\s*(?P<a>.+?)(?=\n\nQ:|\n\nSuhbat|\n\nMijoz|$)",
            user_prompt,
            flags=re.DOTALL,
        )
        if blocks:
            _q, answer = max(blocks, key=lambda row: len(row[1]))[:2]
            return RulesAi._normalize_faq_answer(answer)
        match = re.search(
            r"A:\s*(.+?)(?=\n\nQ:|\n\nSuhbat|\n\nMijoz|$)",
            user_prompt,
            re.IGNORECASE | re.DOTALL,
        )
        if match:
            return RulesAi._normalize_faq_answer(match.group(1))
        return NO_FAQ_FALLBACK

    @staticmethod
    def _normalize_faq_answer(answer: str) -> str:
        text = answer.strip()
        if len(text) > 3500:
            text = text[:3500].rsplit("\n", 1)[0].strip() + "..."
        return text
