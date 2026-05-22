"""FAQ ko'p tilli ustunlar: uz, cyr, ru, en, zh.

Revision ID: 002
Revises: 001
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in (
        "question_uz",
        "answer_uz",
        "question_cyr",
        "answer_cyr",
        "question_ru",
        "answer_ru",
        "question_en",
        "answer_en",
        "question_zh",
        "answer_zh",
    ):
        op.add_column("faq_embeddings", sa.Column(col, sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE faq_embeddings
        SET question_uz = question,
            answer_uz = answer
        WHERE question_uz IS NULL
        """
    )


def downgrade() -> None:
    for col in (
        "question_zh",
        "answer_zh",
        "question_en",
        "answer_en",
        "question_ru",
        "answer_ru",
        "question_cyr",
        "answer_cyr",
        "question_uz",
        "answer_uz",
    ):
        op.drop_column("faq_embeddings", col)
