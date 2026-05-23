"""1688 kategoriyalar — service qatlami (cache orqali)."""

from __future__ import annotations

from typing import List, Optional

from app.core.config import Settings, get_settings
from app.infrastructure.sahiy_api.categories_1688 import (
    Category1688,
    get_categories_1688_cached,
)


class Categories1688Service:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()

    async def list_categories(
        self,
        *,
        parent_id: Optional[int] = None,
        lang: str = "uz_lat",
    ) -> List[Category1688]:
        return await get_categories_1688_cached(
            parent_id=parent_id,
            lang=lang,
            ttl_seconds=self._settings.sahiy_1688_categories_cache_ttl_seconds,
        )
