from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class AiClient(Protocol):
    @property
    def is_available(self) -> bool:
        ...

    async def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
        ...

    def complete_stream(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 1024
    ) -> AsyncIterator[str]:
        ...
