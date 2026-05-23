"""Fetch pickup points from Sahiy API (shared by handlers and Telegram callbacks)."""

from __future__ import annotations

from typing import List, Optional

from app.core.config import Settings, get_settings
from app.infrastructure.sahiy_api.factory import get_sahiy_api_client
from app.infrastructure.sahiy_api.pickup_points import get_pickup_points_cached


class PickupPointsService:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()

    async def fetch_points(self) -> Optional[List[dict]]:
        """Return pickup points or None if API is unavailable."""
        client = get_sahiy_api_client()
        if client is None:
            return None
        return await get_pickup_points_cached(
            client,
            ttl_seconds=self._settings.pickup_points_cache_ttl_seconds,
        )
