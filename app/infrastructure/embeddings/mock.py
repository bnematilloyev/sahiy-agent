"""Deterministic mock embeddings for local development and tests."""

from __future__ import annotations

import hashlib
import math
from typing import List, Optional

from app.core.config import get_settings


class MockEmbedder:
    def __init__(self, dimension: Optional[int] = None) -> None:
        settings = get_settings()
        self._dimension = dimension or settings.embedding_dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> List[float]:
        digest = hashlib.sha256(text.strip().lower().encode("utf-8")).digest()
        values: List[float] = []
        for index in range(self._dimension):
            byte_value = digest[index % len(digest)]
            values.append((byte_value / 127.5) - 1.0)
        return self._normalize(values)

    @staticmethod
    def _normalize(values: List[float]) -> List[float]:
        norm = math.sqrt(sum(v * v for v in values))
        if norm == 0:
            return values
        return [v / norm for v in values]
