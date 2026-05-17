"""Initial schema: chat_sessions, messages, faq_embeddings, tickets + pgvector.

Revision ID: 001
Revises:
Create Date: 2026-05-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("msg_type", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])

    op.create_table(
        "faq_embeddings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tickets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("operator_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tickets_session_id", "tickets", ["session_id"])
    op.create_index("ix_tickets_user_id", "tickets", ["user_id"])

    # IVFFlat index can be added after seeding data (Stage 2)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_faq_embeddings_embedding
        ON faq_embeddings
        USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_faq_embeddings_embedding", table_name="faq_embeddings")
    op.drop_index("ix_tickets_user_id", table_name="tickets")
    op.drop_index("ix_tickets_session_id", table_name="tickets")
    op.drop_table("tickets")
    op.drop_table("faq_embeddings")
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
    op.execute("DROP EXTENSION IF EXISTS vector")
