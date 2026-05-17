from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import MessageRole, ResponseType
from app.main import app
from app.repositories.message_repository import MessageRepository
from app.repositories.ticket_repository import TicketRepository
from tests.fixtures.faq import DEFAULT_FAQ_QUESTION, seed_single_delivery_faq

pytestmark = pytest.mark.asyncio


async def _seed_faq(db_session: AsyncSession) -> None:
    await seed_single_delivery_faq(db_session)
    await db_session.commit()


async def test_process_faq_returns_auto(db_session: AsyncSession):
    await _seed_faq(db_session)

    session_id = uuid.uuid4()
    payload = {
        "session_id": str(session_id),
        "user_id": "user-faq-1",
        "text": DEFAULT_FAQ_QUESTION,
        "context": {"channel": "telegram"},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/process", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "auto"
    assert len(body["text"]) > 10
    assert body.get("ticket_id") is None


async def test_process_ticket_creates_ticket(db_session: AsyncSession):
    session_id = uuid.uuid4()
    payload = {
        "session_id": str(session_id),
        "user_id": "user-ticket-1",
        "text": "Mahsulot buzilgan keldi, pulni qaytaring!",
        "context": {"channel": "telegram"},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/process", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "ticket"
    assert body["ticket_id"] is not None

    ticket_repo = TicketRepository(db_session)
    ticket = await ticket_repo.get_by_id(uuid.UUID(body["ticket_id"]))
    assert ticket is not None
    assert ticket.type == "refund"


async def test_process_ticket_does_not_duplicate_open_ticket(db_session: AsyncSession):
    session_id = uuid.uuid4()
    payload = {
        "session_id": str(session_id),
        "user_id": "user-ticket-dup",
        "text": "Mahsulot buzilgan, pulni qaytaring!",
        "context": {"channel": "web"},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/process", json=payload)
        second = await client.post("/process", json={**payload, "text": "Yana shikoyat qilmoqchiman"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["ticket_id"] == second.json()["ticket_id"]


async def test_process_api_returns_api_type(db_session: AsyncSession):
    session_id = uuid.uuid4()
    payload = {
        "session_id": str(session_id),
        "user_id": "user-api-1",
        "text": "Buyurtmam qayerda, statusini ayting",
        "context": {"channel": "web"},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/process", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "api"
    assert "ORD-TEST" in body["text"] or "buyurtma" in body["text"].lower()


async def test_process_persists_messages(db_session: AsyncSession):
    await _seed_faq(db_session)
    session_id = uuid.uuid4()
    payload = {
        "session_id": str(session_id),
        "user_id": "user-msg-1",
        "text": DEFAULT_FAQ_QUESTION,
        "context": {"channel": "telegram"},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/process", json=payload)

    message_repo = MessageRepository(db_session)
    await db_session.commit()
    messages = await message_repo.list_by_session(session_id)
    assert len(messages) == 2
    assert messages[0].role == MessageRole.USER.value
    assert messages[1].role == MessageRole.ASSISTANT.value
    assert messages[1].msg_type == ResponseType.AUTO.value


async def test_process_rejects_foreign_session(db_session: AsyncSession):
    owner_session = uuid.uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/process",
            json={
                "session_id": str(owner_session),
                "user_id": "owner",
                "text": "Salom",
                "context": {"channel": "api"},
            },
        )
        response = await client.post(
            "/process",
            json={
                "session_id": str(owner_session),
                "user_id": "intruder",
                "text": "Salom",
                "context": {"channel": "api"},
            },
        )

    assert response.status_code == 403
    assert response.json()["error"] == "session_access_denied"
