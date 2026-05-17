#!/usr/bin/env python3
"""Seed FAQ embeddings for local development and RAG testing."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running as `python scripts/seed_faq.py` from project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import dispose_engine, get_session_factory
from app.infrastructure.embeddings.factory import create_embedder
from app.infrastructure.embeddings.mock import MockEmbedder
from app.repositories.faq_repository import FAQRepository


def _get_embedder():
    from app.core.config import get_settings

    if not get_settings().has_openai:
        return MockEmbedder(), "MockEmbedder (no OPENAI_API_KEY)"

    embedder = create_embedder()
    try:
        embedder.embed("test")
        return embedder, type(embedder).__name__
    except Exception as exc:
        create_embedder.cache_clear()
        print(f"OpenAI embedding unavailable ({exc}), using MockEmbedder.")
        return MockEmbedder(), "MockEmbedder (fallback)"

FAQ_SEED_DATA = [
    {
        "question": "Yetkazib berish qancha vaqt oladi?",
        "answer": "Toshkent shahri ichida 1-2 ish kuni, viloyatlarga 3-5 ish kuni.",
        "category": "delivery",
    },
    {
        "question": "Buyurtmani qanday bekor qilaman?",
        "answer": "Buyurtma jo'natilmaguncha profil orqali yoki operatorga murojaat qilib bekor qilishingiz mumkin.",
        "category": "orders",
    },
    {
        "question": "Qanday to'lov usullari mavjud?",
        "answer": "Naqd pul, bank kartasi va Click/Payme orqali to'lash mumkin.",
        "category": "payment",
    },
    {
        "question": "Mahsulotni qaytarish mumkinmi?",
        "answer": "Ha, 14 kun ichida sifatli holatda qaytarish mumkin. Chek va qadoq talab qilinadi.",
        "category": "returns",
    },
    {
        "question": "Mahsulot buzilgan yoki noto'g'ri keldi, nima qilish kerak?",
        "answer": "24 soat ichida foto/video bilan operatorga yozing — almashtiramiz yoki pulni qaytaramiz.",
        "category": "complaints",
    },
    {
        "question": "Kuryer qachon telefon qiladi?",
        "answer": "Yetkazishdan 30-60 daqiqa oldin SMS yoki qo'ng'iroq qilinadi.",
        "category": "delivery",
    },
]


async def seed(clear: bool) -> None:
    embedder, name = _get_embedder()
    print(f"Using embedder: {name}")
    session_factory = get_session_factory()

    async with session_factory() as session:
        repo = FAQRepository(session)

        if clear:
            removed = await repo.delete_all()
            print(f"Cleared {removed} existing FAQ row(s).")

        for item in FAQ_SEED_DATA:
            vector = embedder.embed(item["question"])
            await repo.create(
                question=item["question"],
                answer=item["answer"],
                category=item["category"],
                embedding=vector,
            )

        await session.commit()
        total = await repo.count()
        print(f"Seeded {len(FAQ_SEED_DATA)} FAQ entries. Total in database: {total}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed FAQ embeddings into PostgreSQL.")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Remove all FAQ rows before seeding.",
    )
    args = parser.parse_args()

    async def _run():
        try:
            await seed(clear=args.clear)
        finally:
            await dispose_engine()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
