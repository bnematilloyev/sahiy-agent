from __future__ import annotations

import asyncio
import logging

import anthropic

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, LLMError, LLMTimeoutError

logger = logging.getLogger(__name__)


class ClaudeClient:
    """Anthropic Claude API."""

    def __init__(self, settings: Settings) -> None:
        if not settings.has_anthropic:
            raise ConfigurationError("ANTHROPIC_API_KEY is required for ClaudeClient")
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model
        self._semaphore = asyncio.Semaphore(settings.ai_max_concurrent)
        self._timeout = settings.ai_timeout_seconds

    @property
    def is_available(self) -> bool:
        return True

    async def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
        async with self._semaphore:
            try:
                response = await asyncio.wait_for(
                    self._client.messages.create(
                        model=self._model,
                        max_tokens=max_tokens,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_prompt}],
                    ),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError as exc:
                raise LLMTimeoutError("Claude API request timed out") from exc
            except anthropic.APIError as exc:
                logger.exception("Claude API error")
                raise LLMError(str(exc)) from exc

        for block in response.content:
            if block.type == "text" and block.text.strip():
                return block.text.strip()
        raise LLMError("Claude returned an empty response")
