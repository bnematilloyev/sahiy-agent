from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from app.infrastructure.sahiy_api import categories_1688 as mod
from app.infrastructure.sahiy_api.categories_1688 import Category1688, clear_categories_1688_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_categories_1688_cache()
    yield
    clear_categories_1688_cache()


@pytest.mark.asyncio
async def test_categories_cache_avoids_repeat_fetch():
    sample = [
        Category1688(
            id=1,
            ali_category_id=10,
            ali_parent_id=0,
            name_cn="x",
            name_en="x",
            name_uz="Test",
            name_ru="x",
            leaf=1,
            level=1,
        )
    ]
    fetch = AsyncMock(return_value=sample)
    with patch.object(mod, "fetch_categories_1688", fetch):
        first = await mod.get_categories_1688_cached(ttl_seconds=3600)
        second = await mod.get_categories_1688_cached(ttl_seconds=3600)
    assert len(first) == 1
    assert second == first
    fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_categories_cache_refreshes_after_ttl():
    sample = [
        Category1688(
            id=1,
            ali_category_id=10,
            ali_parent_id=0,
            name_cn="x",
            name_en="x",
            name_uz="Test",
            name_ru="x",
            leaf=1,
            level=1,
        )
    ]
    fetch = AsyncMock(return_value=sample)
    with patch.object(mod, "fetch_categories_1688", fetch):
        await mod.get_categories_1688_cached(ttl_seconds=1)
        mod._cache["root"] = (sample, time.time() - 10)
        await mod.get_categories_1688_cached(ttl_seconds=1)
    assert fetch.await_count == 2
