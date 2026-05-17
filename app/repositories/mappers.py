"""Maps ORM models to domain entities — keeps persistence separate from business layer."""

from __future__ import annotations

from app.db.models import ChatSessionModel, FAQEmbeddingModel, MessageModel, TicketModel
from app.domain.entities import ChatSession, FAQEntry, Message, Ticket


def to_chat_session(model: ChatSessionModel) -> ChatSession:
    return ChatSession(
        id=model.id,
        user_id=model.user_id,
        channel=model.channel,
        status=model.status,
        created_at=model.created_at,
    )


def to_message(model: MessageModel) -> Message:
    return Message(
        id=model.id,
        session_id=model.session_id,
        role=model.role,
        content=model.content,
        msg_type=model.msg_type,
        created_at=model.created_at,
    )


def to_faq_entry(model: FAQEmbeddingModel, similarity: float = 0.0) -> FAQEntry:
    return FAQEntry(
        id=model.id,
        question=model.question,
        answer=model.answer,
        category=model.category,
        similarity=similarity,
    )


def to_ticket(model: TicketModel) -> Ticket:
    return Ticket(
        id=model.id,
        session_id=model.session_id,
        user_id=model.user_id,
        type=model.type,
        status=model.status,
        operator_id=model.operator_id,
        created_at=model.created_at,
    )
