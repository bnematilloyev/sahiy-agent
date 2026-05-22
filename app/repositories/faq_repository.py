from __future__ import annotations

from typing import List, Optional

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import FAQEmbeddingModel
from app.domain.entities import FAQEntry
from app.repositories.base import BaseRepository
from app.repositories.mappers import to_faq_entry


class FAQRepository(BaseRepository):
    async def create(
        self,
        question: str,
        answer: str,
        category: str,
        embedding: List[float],
    ) -> FAQEntry:
        model = FAQEmbeddingModel(
            question=question,
            answer=answer,
            category=category,
            embedding=embedding,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return to_faq_entry(model)

    async def search_similar(
        self,
        embedding: List[float],
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> List[FAQEntry]:
        settings = get_settings()
        limit = top_k or settings.rag_top_k
        min_similarity = threshold if threshold is not None else settings.rag_similarity_threshold

        distance_expr = FAQEmbeddingModel.embedding.cosine_distance(embedding)
        similarity_expr = (1 - distance_expr).label("similarity")

        stmt = (
            select(FAQEmbeddingModel, similarity_expr)
            .where(FAQEmbeddingModel.embedding.is_not(None))
            .order_by(distance_expr)
            .limit(limit)
        )
        result = await self._session.execute(stmt)

        entries: List[FAQEntry] = []
        for model, similarity in result.all():
            score = float(similarity)
            if score >= min_similarity:
                entries.append(to_faq_entry(model, similarity=score))
        return entries

    async def count(self) -> int:
        stmt = select(func.count()).select_from(FAQEmbeddingModel)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_missing_embeddings(self) -> int:
        stmt = (
            select(func.count())
            .select_from(FAQEmbeddingModel)
            .where(FAQEmbeddingModel.embedding.is_(None))
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_missing_embeddings(self) -> List[FAQEntry]:
        stmt = select(FAQEmbeddingModel).where(FAQEmbeddingModel.embedding.is_(None))
        result = await self._session.execute(stmt)
        return [to_faq_entry(row) for row in result.scalars().all()]

    async def list_all(self) -> List[FAQEntry]:
        stmt = select(FAQEmbeddingModel).order_by(FAQEmbeddingModel.id)
        result = await self._session.execute(stmt)
        return [to_faq_entry(row) for row in result.scalars().all()]

    async def search_by_keywords(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
    ) -> List[FAQEntry]:
        """Fallback when vectors are missing or similarity is too low (mock embedder)."""
        settings = get_settings()
        limit = top_k or settings.rag_top_k
        stop = {
            "qancha",
            "qanday",
            "nima",
            "uchun",
            "bilan",
            "qayerda",
            "kerak",
            "mumkin",
            "haqida",
            "bo'ladi",
            "qiladi",
        }
        tokens = [t for t in query.lower().split() if len(t) >= 3 and t not in stop]
        if not tokens:
            return []

        text_columns = (
            FAQEmbeddingModel.question,
            FAQEmbeddingModel.answer,
            FAQEmbeddingModel.question_uz,
            FAQEmbeddingModel.answer_uz,
            FAQEmbeddingModel.question_cyr,
            FAQEmbeddingModel.answer_cyr,
            FAQEmbeddingModel.question_ru,
            FAQEmbeddingModel.answer_ru,
            FAQEmbeddingModel.question_en,
            FAQEmbeddingModel.answer_en,
            FAQEmbeddingModel.question_zh,
            FAQEmbeddingModel.answer_zh,
        )
        clauses = []
        for token in tokens[:8]:
            pattern = f"%{token}%"
            for col in text_columns:
                clauses.append(col.ilike(pattern))

        stmt = select(FAQEmbeddingModel).where(or_(*clauses)).limit(max(limit * 10, 30))
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())

        scored: list[tuple[int, int, FAQEmbeddingModel]] = []
        for row in rows:
            question_blob = " ".join(
                filter(
                    None,
                    (
                        row.question,
                        row.question_uz,
                        row.question_cyr,
                        row.question_ru,
                        row.question_en,
                        row.question_zh,
                    ),
                )
            ).lower()
            answer_blob = " ".join(
                filter(
                    None,
                    (
                        row.answer,
                        row.answer_uz,
                        row.answer_cyr,
                        row.answer_ru,
                        row.answer_en,
                        row.answer_zh,
                    ),
                )
            ).lower()
            q_hits = sum(2 for token in tokens if token in question_blob)
            a_hits = sum(1 for token in tokens if token in answer_blob)
            total = q_hits + a_hits
            if q_hits >= 2 or total >= 3:
                scored.append((q_hits, total, row))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [
            to_faq_entry(row, similarity=0.70 + 0.03 * min(total, 6))
            for _q_hits, total, row in scored[:limit]
        ]

    async def update_embedding(self, faq_id: int, embedding: List[float]) -> None:
        stmt = select(FAQEmbeddingModel).where(FAQEmbeddingModel.id == faq_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"FAQ id={faq_id} not found")
        model.embedding = embedding
        await self._session.flush()

    async def delete_all(self) -> int:
        count_before = await self.count()
        await self._session.execute(delete(FAQEmbeddingModel))
        await self._session.flush()
        return count_before
