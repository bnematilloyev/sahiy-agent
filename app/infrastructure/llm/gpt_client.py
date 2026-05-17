from __future__ import annotations

import asyncio
import logging

from openai import AsyncOpenAI, OpenAIError

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, LLMError, LLMTimeoutError

logger = logging.getLogger(__name__)


class GptClient:
    """OpenAI Chat Completions (GPT-4o, gpt-4o-mini, ...)."""

    def __init__(self, settings: Settings) -> None:
        if not settings.has_openai:
            raise ConfigurationError("OPENAI_API_KEY is required for GptClient")
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model
        self._semaphore = asyncio.Semaphore(settings.ai_max_concurrent)
        self._timeout = settings.ai_timeout_seconds

    @property
    def is_available(self) -> bool:
        return True

    async def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
        async with self._semaphore:
            try:
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        model=self._model,
                        max_tokens=max_tokens,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    ),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError as exc:
                raise LLMTimeoutError("OpenAI request timed out") from exc
            except OpenAIError as exc:
                logger.exception("OpenAI API error")
                raise LLMError(str(exc)) from exc

        content = response.choices[0].message.content
        if content and content.strip():
            return content.strip()
        raise LLMError("GPT returned an empty response")
