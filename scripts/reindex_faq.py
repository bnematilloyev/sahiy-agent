#!/usr/bin/env python3
"""Generate embeddings for FAQ rows imported without vectors (SQL/GUI)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import dispose_engine, get_session_factory
from app.infrastructure.embeddings.factory import create_embedder
from app.infrastructure.embeddings.mock import MockEmbedder
from app.repositories.faq_repository import FAQRepository


def _get_embedder():
    from app.core.config import get_settings
    from app.infrastructure.embeddings.factory import create_embedder as _create

    if not get_settings().has_openai:
        return MockEmbedder(), "MockEmbedder (no OPENAI_API_KEY)"

    embedder = _create()
    try:
        embedder.embed("test")
        return embedder, type(embedder).__name__
    except Exception as exc:
        _create.cache_clear()
        print(f"OpenAI embedding unavailable ({exc}), using MockEmbedder.")
        return MockEmbedder(), "MockEmbedder (fallback)"


async def reindex(*, force: bool) -> None:
    embedder, name = _get_embedder()
    print(f"Using embedder: {name}")

    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = FAQRepository(session)

        if force:
            rows = await repo.list_all()
            print(f"Re-embedding all {len(rows)} FAQ row(s).")
        else:
            missing = await repo.count_missing_embeddings()
            if missing == 0:
                print("All FAQ rows already have embeddings. Use --force to rebuild.")
                return
            rows = await repo.list_missing_embeddings()
            print(f"Embedding {len(rows)} FAQ row(s) without vectors.")

        for index, entry in enumerate(rows, start=1):
            vector = embedder.embed(entry.question)
            await repo.update_embedding(entry.id, vector)
            if index % 20 == 0 or index == len(rows):
                print(f"  {index}/{len(rows)} done")

        await session.commit()
        remaining = await repo.count_missing_embeddings()
        total = await repo.count()
        print(f"Done. Total FAQ: {total}, missing embeddings: {remaining}.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill pgvector embeddings for faq_embeddings rows.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed every FAQ row, not only rows with NULL embedding.",
    )
    args = parser.parse_args()

    async def _run():
        try:
            await reindex(force=args.force)
        finally:
            await dispose_engine()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
