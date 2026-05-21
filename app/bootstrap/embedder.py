"""Shared embedder resolution for CLI seed/reindex scripts."""

from __future__ import annotations

from typing import Tuple

from app.core.config import get_settings
from app.infrastructure.embeddings.factory import create_embedder
from app.infrastructure.embeddings.mock import MockEmbedder
from app.infrastructure.embeddings.ports import Embedder


def resolve_embedder(*, verbose: bool = False) -> Tuple[Embedder, str]:
    settings = get_settings()
    if not settings.has_openai or settings.resolved_embedding_provider() == "mock":
        return MockEmbedder(), "MockEmbedder"

    embedder = create_embedder()
    try:
        embedder.embed("test")
        return embedder, type(embedder).__name__
    except Exception as exc:
        create_embedder.cache_clear()
        if verbose:
            print("\n⚠️  OpenAI embedding ishlamadi — MockEmbedder ishlatiladi.")
            print(f"   Sabab: {exc}")
            print(
                "   RAG qidiruv so'z bo'yicha ishlaydi (semantik emas). "
                "OpenAI balans to'ldirgach: EMBEDDING_PROVIDER=openai va qayta seed.\n"
            )
        else:
            print(f"OpenAI embedding unavailable ({exc}), using MockEmbedder.")
        return MockEmbedder(), "MockEmbedder (fallback)"
