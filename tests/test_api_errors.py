from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.asyncio


async def test_validation_error_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/process", json={"text": "missing fields"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_error"
    assert "request_id" in body


async def test_health_includes_request_id_header():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": "test-req-1"})

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "test-req-1"
