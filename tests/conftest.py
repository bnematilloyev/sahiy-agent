from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import config
from app.core.database import dispose_engine, get_session_factory
from app.infrastructure.embeddings.factory import create_embedder
from app.infrastructure.llm.factory import create_ai_client


@pytest.fixture(autouse=True)
def test_settings(monkeypatch):
    """Isolate tests from developer .env (OpenAI keys, provider choice)."""
    monkeypatch.setenv("AI_PROVIDER", "rules")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("SESSION_IDLE_HOURS", "0")
    monkeypatch.setenv("SAHIY_API_BASE_URL", "")
    monkeypatch.setenv("SERVICE_USER_PHONE", "")
    monkeypatch.setenv("SERVICE_USER_PASSWORD", "")
    config.get_settings.cache_clear()
    from app.infrastructure.sahiy_api.factory import clear_sahiy_api_cache

    clear_sahiy_api_cache()
    yield
    config.get_settings.cache_clear()
    clear_sahiy_api_cache()


@pytest.fixture(autouse=True)
def clear_factory_caches():
    create_ai_client.cache_clear()
    create_embedder.cache_clear()
    yield
    create_ai_client.cache_clear()
    create_embedder.cache_clear()


@pytest.fixture(autouse=True)
async def reset_db_engine():
    await dispose_engine()
    yield
    await dispose_engine()


@pytest.fixture
async def db_session() -> AsyncSession:
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
