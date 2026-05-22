#!/usr/bin/env python3
"""
Upsert Sahiy FAQ (142 base + 46 quick_replies type 1/2) and generate embeddings.

Use when rows were inserted manually via SQL without vectors:
  python scripts/seed_faq_sahiy.py          # upsert text + embed
  python scripts/seed_faq_sahiy.py --embed-only   # only refresh embeddings
  python scripts/seed_faq_sahiy.py --clear        # delete all, insert fresh
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text

from app.bootstrap.embedder import resolve_embedder
from app.infrastructure.embeddings.factory import create_embedder
from app.core.database import dispose_engine, get_session_factory
from app.db.models import FAQEmbeddingModel
from app.domain.faq_locale import apply_i18n_to_model, faq_embed_text, normalize_faq_seed_item
from app.repositories.faq_repository import FAQRepository
from scripts.data.faq_100 import FAQ_ENTRIES
from scripts.data.faq_quick_replies import QUICK_REPLY_FAQ_ENTRIES

FAQ_ENTRIES_ALL = FAQ_ENTRIES + QUICK_REPLY_FAQ_ENTRIES


def _assert_unique_faq_ids() -> None:
    seen: dict[int, str] = {}
    for item in FAQ_ENTRIES_ALL:
        row = normalize_faq_seed_item(item)
        faq_id = int(row["id"])
        label = row["question_uz"]
        if faq_id in seen:
            raise ValueError(
                f"Duplicate FAQ id={faq_id}: {seen[faq_id]!r} and {label!r}"
            )
        seen[faq_id] = label


async def _reset_id_sequence(session) -> None:
    await session.execute(
        text(
            "SELECT setval("
            "pg_get_serial_sequence('faq_embeddings', 'id'), "
            "COALESCE((SELECT MAX(id) FROM faq_embeddings), 1)"
            ")"
        )
    )


def _new_model(faq_id: int, item: dict, vector: list[float]) -> FAQEmbeddingModel:
    model = FAQEmbeddingModel(id=faq_id, embedding=vector)
    apply_i18n_to_model(model, item)
    return model


async def seed(*, clear: bool, embed_only: bool) -> None:
    _assert_unique_faq_ids()
    embedder, embedder_name = resolve_embedder(verbose=True)
    print(f"Using embedder: {embedder_name}")
    print(
        f"FAQ entries in seed file: {len(FAQ_ENTRIES_ALL)} "
        f"(base {len(FAQ_ENTRIES)} + quick_replies {len(QUICK_REPLY_FAQ_ENTRIES)})"
    )

    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = FAQRepository(session)

        if clear:
            removed = await repo.delete_all()
            await session.commit()
            print(f"Cleared {removed} existing row(s).")

        for index, raw in enumerate(FAQ_ENTRIES_ALL, start=1):
            item = normalize_faq_seed_item(raw)
            faq_id = item["id"]
            vector = embedder.embed(faq_embed_text(item))

            if not clear and not embed_only:
                existing = await session.get(FAQEmbeddingModel, faq_id)
                if existing:
                    apply_i18n_to_model(existing, item)
                    existing.embedding = vector
                else:
                    session.add(_new_model(faq_id, item, vector))
            elif embed_only:
                existing = await session.get(FAQEmbeddingModel, faq_id)
                if existing:
                    existing.embedding = vector
                else:
                    print(f"  skip id={faq_id} (not in DB)")
                    continue
            else:
                session.add(_new_model(faq_id, item, vector))

            if index % 20 == 0 or index == len(FAQ_ENTRIES_ALL):
                print(f"  {index}/{len(FAQ_ENTRIES_ALL)} processed")

        await _reset_id_sequence(session)
        await session.commit()

        total = await repo.count()
        missing = await repo.count_missing_embeddings()
        print(f"Done. Total in DB: {total}, missing embeddings: {missing}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed/upsert Sahiy FAQ with vectors.")
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
