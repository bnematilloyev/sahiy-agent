from __future__ import annotations

from typing import List, Protocol


class Embedder(Protocol):
    @property
    def dimension(self) -> int:
        ...

    def embed(self, text: str) -> List[float]:
        ...
