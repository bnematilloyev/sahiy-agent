from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.core.exceptions import ConfigurationError
from app.infrastructure.embeddings.fallback_embedder import FallbackEmbedder
from app.infrastructure.embeddings.mock import MockEmbedder
from app.infrastructure.embeddings.openai_embedder import OpenAiEmbedder
from app.infrastructure.embeddings.ports import Embedder


@lru_cache
def create_embedder() -> Embedder:
    settings = get_settings()
    chain = settings.embedding_chain_providers()
    mock = MockEmbedder()

    if not chain or chain == ["mock"]:
        return mock

    if "openai" in chain:
        if not settings.has_openai:
            if "mock" in chain:
                return mock
            raise ConfigurationError(
                "EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is empty"
            )
        primary = OpenAiEmbedder(settings)
        if "mock" in chain:
            return FallbackEmbedder(primary=primary, fallback=mock)
        return primary

    raise ConfigurationError(
        f"Unknown embedding chain: {chain} (EMBEDDING_PROVIDER={settings.embedding_provider})"
    )
