from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import List

from app.core.exceptions import LLMError, LLMTimeoutError
from app.core.provider_errors import is_billing_or_auth_error
from app.core.prompts import CLASSIFIER_MARKER, RAG_SYSTEM
from app.infrastructure.llm.ports import AiClient
from app.infrastructure.llm.rules_ai import RulesAi

logger = logging.getLogger(__name__)


class ChainedAiClient:
    """Try providers in order (e.g. Anthropic → OpenAI), then rules for classify/RAG."""

    def __init__(self, providers: List[AiClient]) -> None:
        if not providers:
            raise ValueError("ChainedAiClient requires at least one provider")
        self._providers = providers
        self._rules = RulesAi()

    @property
    def is_available(self) -> bool:
        return any(provider.is_available for provider in self._providers)

    async def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
        last_error: Exception | None = None
        for index, provider in enumerate(self._providers):
            if not provider.is_available:
                continue
            try:
                return await provider.complete(
                    system_prompt, user_prompt, max_tokens=max_tokens
                )
            except (LLMTimeoutError, LLMError) as exc:
                last_error = exc
                name = type(provider).__name__
                if is_billing_or_auth_error(exc):
                    logger.warning(
                        "LLM provider %s unavailable (quota/billing/auth): %s",
                        name,
                        exc,
                    )
                else:
                    logger.warning("LLM provider %s failed: %s", name, exc)
                if index < len(self._providers) - 1:
                    logger.info("Trying next LLM provider in chain")

        if CLASSIFIER_MARKER in system_prompt or system_prompt == RAG_SYSTEM:
            logger.warning("All LLM providers failed, using rules fallback")
            return await self._rules.complete(system_prompt, user_prompt, max_tokens=max_tokens)

        if last_error:
            raise last_error
        raise LLMError("No LLM provider available")

    async def complete_stream(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 1024
    ) -> AsyncIterator[str]:
        last_error: Exception | None = None
        for index, provider in enumerate(self._providers):
            if not provider.is_available:
                continue
            try:
                async for token in provider.complete_stream(
                    system_prompt, user_prompt, max_tokens=max_tokens
                ):
                    yield token
                return
            except (LLMTimeoutError, LLMError) as exc:
                last_error = exc
                name = type(provider).__name__
                if is_billing_or_auth_error(exc):
                    logger.warning(
                        "LLM stream %s unavailable (quota/billing/auth): %s",
                        name,
                        exc,
                    )
                else:
                    logger.warning("LLM stream %s failed: %s", name, exc)
                if index < len(self._providers) - 1:
                    logger.info("Trying next LLM provider in chain (stream)")

        if CLASSIFIER_MARKER in system_prompt or system_prompt == RAG_SYSTEM:
            logger.warning("All LLM stream providers failed, using rules fallback")
            text = await self._rules.complete(system_prompt, user_prompt, max_tokens=max_tokens)
            yield text
            return

        if last_error:
            raise last_error
        raise LLMError("No LLM provider available")
