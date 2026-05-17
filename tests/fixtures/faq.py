from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.embeddings.mock import MockEmbedder
from app.repositories.faq_repository import FAQRepository

DEFAULT_FAQ_QUESTION = "Yetkazib berish qancha vaqt oladi?"
DEFAULT_FAQ_ANSWER = "Toshkent ichida 1-2 kun, viloyatlarga 3-5 kun."


async def seed_single_delivery_faq(
    db_session: AsyncSession,
    question: str = DEFAULT_FAQ_QUESTION,
    answer: str = DEFAULT_FAQ_ANSWER,
) -> None:
    embedder = MockEmbedder()
    repo = FAQRepository(db_session)
    await repo.create(
        question=question,
        answer=answer,
        category="delivery",
        embedding=embedder.embed(question),
    )
