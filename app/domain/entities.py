from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class ChatSession:
    id: UUID
    user_id: str
    channel: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class Message:
    id: UUID
    session_id: UUID
    role: str
    content: str
    msg_type: str | None
    created_at: datetime


@dataclass(frozen=True)
class FAQEntry:
    id: int
    question: str
    answer: str
    category: str
    similarity: float = field(default=0.0)
    question_uz: str | None = None
    answer_uz: str | None = None
    question_cyr: str | None = None
    answer_cyr: str | None = None
    question_ru: str | None = None
    answer_ru: str | None = None
    question_en: str | None = None
    answer_en: str | None = None
    question_zh: str | None = None
    answer_zh: str | None = None


@dataclass(frozen=True)
class Ticket:
    id: UUID
    session_id: UUID
    user_id: str
    type: str
    status: str
    operator_id: str | None
    created_at: datetime
