"""Order status lookup — Sahiy service_user API or Go internal fallback."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union

import httpx

from app.core.config import Settings
from app.infrastructure.sahiy_api.customer import CustomerApi, CustomerSnapshot
from app.infrastructure.sahiy_api.factory import get_sahiy_customer_api

logger = logging.getLogger(__name__)


class OrderApi:
    def __init__(self, settings: Settings, customer_api: Optional[CustomerApi] = None) -> None:
        self._settings = settings
        self._base_url = settings.go_backend_url.rstrip("/")
        self._timeout = settings.go_backend_timeout_seconds
        self._customer = customer_api if customer_api is not None else get_sahiy_customer_api()

    async def lookup(
        self,
        user_id: str,
        query: str,
        session_id: Optional[str] = None,
        *,
        phone: Optional[str] = None,
        sahiy_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if self._customer is not None:
            return await self._lookup_sahiy(
                query,
                phone=phone,
                sahiy_user_id=sahiy_user_id,
            )

        return await self._lookup_go(user_id, query, session_id)

    async def _lookup_sahiy(
        self,
        query: str,
        *,
        phone: Optional[str] = None,
        sahiy_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        # Telegram channel user_id is NOT Sahiy DB user_id — use phone or explicit sahiy_user_id.
        logger.info(
            "Sahiy order lookup phone=%s sahiy_user_id=%s query=%r",
            phone,
            sahiy_user_id,
            query[:80],
        )
        result = await self._customer.lookup(
            verified_user_id=sahiy_user_id,
            phone=phone,
            query=query,
        )
        if isinstance(result, dict) and result.get("error"):
            return result
        if isinstance(result, CustomerSnapshot):
            return result.to_api_payload()
        return {"error": "unknown", "message": "Ma'lumot olinmadi."}

    async def _lookup_go(
        self,
        user_id: str,
        query: str,
        session_id: Optional[str],
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

