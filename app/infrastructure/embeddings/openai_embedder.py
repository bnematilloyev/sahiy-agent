from __future__ import annotations

from typing import List, Optional

from openai import OpenAI

from app.core.config import Settings


class OpenAiEmbedder:
    """OpenAI embeddings for FAQ vector search (1536 dims with text-embedding-3-small)."""

    def __init__(self, settings: Settings, dimension: Optional[int] = None) -> None:
        if not settings.has_openai:
            raise ValueError("OPENAI_API_KEY is required for OpenAiEmbedder")
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_embedding_model
        self._dimension = dimension or settings.embedding_dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> List[float]:
        response = self._client.embeddings.create(
            model=self._model,
            input=text.strip(),
        )
        return list(response.data[0].embedding)
