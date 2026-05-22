from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.core.database import Base

_settings = get_settings()
_EMBEDDING_DIM = _settings.embedding_dimension


class ChatSessionModel(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="telegram")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    messages: Mapped[List["MessageModel"]] = relationship(
        back_populates="session", lazy="selectin"
    )
    tickets: Mapped[List["TicketModel"]] = relationship(
        back_populates="session", lazy="selectin"
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    msg_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["ChatSessionModel"] = relationship(back_populates="messages")


class FAQEmbeddingModel(Base):
    __tablename__ = "faq_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="general")
    question_uz: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answer_uz: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question_cyr: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answer_cyr: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question_ru: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answer_ru: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answer_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question_zh: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answer_zh: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(_EMBEDDING_DIM), nullable=True)


class TicketModel(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    operator_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["ChatSessionModel"] = relationship(back_populates="tickets")
