from __future__ import annotations

import re

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

    @staticmethod
    def _answer_from_faq(user_prompt: str) -> str:
        blocks = re.findall(
            r"Q:\s*(?P<q>.+?)\nA:\s*(?P<a>.+?)\n\(category:.*?similarity:\s*(?P<s>[\d.]+)\)",
            user_prompt,
            flags=re.DOTALL,
        )
        if blocks:
            _q, answer, _score = max(blocks, key=lambda row: float(row[2]))
            compact = " ".join(answer.split())
            sentences = re.split(r"(?<=[.!?])\s+", compact)
            short = " ".join(sentences[:2]).strip() or compact
            if len(short) > 320:
                short = short[:320].rsplit(" ", 1)[0] + "..."
            return short
        match = re.search(r"A:\s*(.+)", user_prompt, re.IGNORECASE | re.DOTALL)
        if match:
            compact = " ".join(match.group(1).strip().split())
            sentences = re.split(r"(?<=[.!?])\s+", compact)
            return " ".join(sentences[:2]).strip() or compact[:320]
        return NO_FAQ_FALLBACK
