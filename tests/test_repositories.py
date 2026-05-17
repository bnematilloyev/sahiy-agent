from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import MessageRole, ResponseType, SessionStatus, TicketStatus
from app.infrastructure.embeddings.mock import MockEmbedder
from app.repositories.faq_repository import FAQRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.session_repository import ChatSessionRepository
from app.repositories.ticket_repository import TicketRepository

pytestmark = pytest.mark.asyncio


async def test_open_session_reuses_active(db_session: AsyncSession):
    repo = ChatSessionRepository(db_session)
    user_id = f"test-user-{uuid.uuid4()}"

    first = await repo.open_session(user_id=user_id, channel="telegram")
    second = await repo.open_session(user_id=user_id, channel="telegram")

    assert first.id == second.id
    assert first.status == SessionStatus.ACTIVE.value


async def test_message_repository_stores_history(db_session: AsyncSession):
    session_repo = ChatSessionRepository(db_session)
    message_repo = MessageRepository(db_session)

    chat = await session_repo.create(user_id="msg-user", channel="telegram")
    await message_repo.create(
        session_id=chat.id,
        role=MessageRole.USER.value,
        content="Salom",
    )
    await message_repo.create(
        session_id=chat.id,
        role=MessageRole.ASSISTANT.value,
        content="Assalomu alaykum!",
        msg_type=ResponseType.AUTO.value,
    )

    messages = await message_repo.list_by_session(chat.id)
    assert len(messages) == 2
    assert messages[0].role == MessageRole.USER.value
    assert messages[1].msg_type == ResponseType.AUTO.value


async def test_faq_vector_search_finds_exact_question(db_session: AsyncSession):
    embedder = MockEmbedder()
    faq_repo = FAQRepository(db_session)

    question = "Yetkazib berish qancha vaqt oladi?"
    vector = embedder.embed(question)
    await faq_repo.create(
        question=question,
        answer="Toshkent ichida 1-2 kun.",
        category="delivery",
        embedding=vector,
    )

    results = await faq_repo.search_similar(
        embedding=embedder.embed(question),
        top_k=3,
        threshold=0.85,
    )

    assert len(results) >= 1
    assert results[0].question == question
    assert results[0].similarity >= 0.85


async def test_ticket_repository_create_and_list(db_session: AsyncSession):
    session_repo = ChatSessionRepository(db_session)
    ticket_repo = TicketRepository(db_session)

    chat = await session_repo.create(user_id="ticket-user", channel="telegram")
    ticket = await ticket_repo.create(
        session_id=chat.id,
        user_id="ticket-user",
        ticket_type="refund",
    )

    tickets = await ticket_repo.list_by_session(chat.id)
    assert len(tickets) == 1
    assert tickets[0].id == ticket.id
    assert tickets[0].status == TicketStatus.OPEN.value

    updated = await ticket_repo.update_status(ticket.id, TicketStatus.IN_PROGRESS.value)
    assert updated is not None
    assert updated.status == TicketStatus.IN_PROGRESS.value
