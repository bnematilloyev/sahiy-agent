from __future__ import annotations

from typing import Protocol


class AiClient(Protocol):
    @property
    def is_available(self) -> bool:
        ...

    async def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
        ...
