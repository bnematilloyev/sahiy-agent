from __future__ import annotations

import logging

from app.core.exceptions import LLMError, LLMTimeoutError
from app.core.prompts import CLASSIFIER_MARKER, RAG_SYSTEM
from app.infrastructure.llm.ports import AiClient

logger = logging.getLogger(__name__)


class ResilientAiClient:
    """Try GPT/Claude first; on API errors fall back to RulesAi."""

    def __init__(self, primary: AiClient, fallback: AiClient) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def is_available(self) -> bool:
        return self._primary.is_available

    async def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
        try:
            return await self._primary.complete(system_prompt, user_prompt, max_tokens=max_tokens)
        except (LLMTimeoutError, LLMError) as exc:
            if CLASSIFIER_MARKER in system_prompt or system_prompt == RAG_SYSTEM:
                logger.warning("Primary LLM failed, using rules fallback: %s", exc)
                return await self._fallback.complete(
                    system_prompt, user_prompt, max_tokens=max_tokens
                )
            raise
