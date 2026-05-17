"""HTTP client for order status from Go backend."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class OrderApi:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.go_backend_url.rstrip("/")
        self._timeout = settings.go_backend_timeout_seconds

    async def lookup(
        self,
        user_id: str,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/internal/ai/order-lookup",
                    json={"user_id": user_id, "session_id": session_id, "query": query},
                )
                if response.status_code == 200:
                    return response.json()
                logger.warning(
                    "Order API returned %s: %s",
                    response.status_code,
                    response.text[:200],
                )
        except httpx.HTTPError as exc:
            logger.warning("Order API unavailable: %s", exc)

        return self._demo_data(user_id)

    @staticmethod
    def _demo_data(user_id: str) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "order_id": "ORD-TEST-1001",
            "status": "in_transit",
            "status_label": "Yo'lda",
            "eta": "2 kun",
            "note": "Demo data — Go backend ulanmagan",
        }
