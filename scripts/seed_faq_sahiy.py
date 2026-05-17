#!/usr/bin/env python3
"""
Upsert Sahiy FAQ (142 entries) and generate embeddings.

Use when rows were inserted manually via SQL without vectors:
  python scripts/seed_faq_sahiy.py          # upsert text + embed
  python scripts/seed_faq_sahiy.py --embed-only   # only refresh embeddings
  python scripts/seed_faq_sahiy.py --clear        # delete all, insert 140 fresh
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text

from app.core.database import dispose_engine, get_session_factory
from app.db.models import FAQEmbeddingModel
from app.infrastructure.embeddings.factory import create_embedder
from app.infrastructure.embeddings.mock import MockEmbedder
from app.repositories.faq_repository import FAQRepository
from scripts.data.faq_100 import FAQ_ENTRIES


def _get_embedder():
    from app.core.config import get_settings
    from app.infrastructure.embeddings.factory import create_embedder as _create
    from app.infrastructure.embeddings.openai_embedder import OpenAiEmbedder

    settings = get_settings()
    provider = settings.resolved_embedding_provider()

    if provider == "mock" or not settings.has_openai:
        return MockEmbedder(), "MockEmbedder"

    try:
        OpenAiEmbedder(settings).embed("test")
    except Exception as exc:
        _create.cache_clear()
        print("\n⚠️  OpenAI embedding ishlamadi — MockEmbedder ishlatiladi.")
        print(f"   Sabab: {exc}")
        print(
            "   RAG qidiruv so'z bo'yicha ishlaydi (semantik emas). "
            "OpenAI balans to'ldirgach: EMBEDDING_PROVIDER=openai va qayta seed.\n"
        )
        return MockEmbedder(), "MockEmbedder (OpenAI unavailable)"

    embedder = _create()
    return embedder, "OpenAiEmbedder (+ mock fallback on error)"


async def _reset_id_sequence(session) -> None:
    await session.execute(
        text(
            "SELECT setval("
            "pg_get_serial_sequence('faq_embeddings', 'id'), "
            "COALESCE((SELECT MAX(id) FROM faq_embeddings), 1)"
            ")"
        )
    )


async def seed(*, clear: bool, embed_only: bool) -> None:
    embedder, embedder_name = _get_embedder()
    print(f"Using embedder: {embedder_name}")
    print(f"FAQ entries in seed file: {len(FAQ_ENTRIES)}")

    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = FAQRepository(session)

        if clear:
            removed = await repo.delete_all()
            print(f"Cleared {removed} existing row(s).")

        for index, item in enumerate(FAQ_ENTRIES, start=1):
            faq_id = item["id"]
            vector = embedder.embed(item["question"])

            if not clear and not embed_only:
                existing = await session.get(FAQEmbeddingModel, faq_id)
                if existing:
                    existing.question = item["question"]
                    existing.answer = item["answer"]
                    existing.category = item["category"]
                    existing.embedding = vector
                else:
                    session.add(
                        FAQEmbeddingModel(
                            id=faq_id,
                            question=item["question"],
                            answer=item["answer"],
                            category=item["category"],
                            embedding=vector,
                        )
                    )
            elif embed_only:
                existing = await session.get(FAQEmbeddingModel, faq_id)
                if existing:
                    existing.embedding = vector
                else:
                    print(f"  skip id={faq_id} (not in DB)")
                    continue
            else:
                session.add(
                    FAQEmbeddingModel(
                        id=faq_id,
                        question=item["question"],
                        answer=item["answer"],
                        category=item["category"],
                        embedding=vector,
                    )
                )

            if index % 20 == 0 or index == len(FAQ_ENTRIES):
                print(f"  {index}/{len(FAQ_ENTRIES)} processed")

        await _reset_id_sequence(session)
        await session.commit()

        total = await repo.count()
        missing = await repo.count_missing_embeddings()
        print(f"Done. Total in DB: {total}, missing embeddings: {missing}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed/upsert Sahiy 142 FAQ with vectors.")
    parser.add_argument("--clear", action="store_true", help="Delete all FAQs before insert.")
    parser.add_argument(
        "--embed-only",
        action="store_true",
        help="Only set embeddings for existing ids (keep question/answer as in DB).",
    )
    args = parser.parse_args()

    async def _run():
        try:
            await seed(clear=args.clear, embed_only=args.embed_only)
        finally:
            await dispose_engine()
            create_embedder.cache_clear()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
