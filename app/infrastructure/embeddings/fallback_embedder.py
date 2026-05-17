from __future__ import annotations

import logging
from typing import List

from app.core.provider_errors import is_billing_or_auth_error
from app.infrastructure.embeddings.ports import Embedder

logger = logging.getLogger(__name__)


class FallbackEmbedder:
    """Use primary embedder; on API errors fall back to mock vectors."""

    def __init__(self, primary: Embedder, fallback: Embedder) -> None:
        self._primary = primary
        self._fallback = fallback
        self._force_fallback = False
        self._warned = False

    @property
    def dimension(self) -> int:
        return self._primary.dimension

    def embed(self, text: str) -> List[float]:
        if self._force_fallback:
            return self._fallback.embed(text)

        try:
            return self._primary.embed(text)
        except Exception as exc:
            if not self._warned:
                logger.warning("Embedding failed, using mock fallback: %s", exc)
                self._warned = True
            if is_billing_or_auth_error(exc):
                self._force_fallback = True
                logger.warning(
                    "OpenAI embeddings disabled for this run (quota/auth). "
                    "Set EMBEDDING_PROVIDER=mock or add OpenAI billing, then reindex."
                )
            return self._fallback.embed(text)
