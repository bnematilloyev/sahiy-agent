"""Daigou orders — Xitoy omborigacha (analytics API)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.infrastructure.sahiy_api.client import SahiyApiClient

logger = logging.getLogger(__name__)

DAIGOU_ANALYTICS_PATH = "/api/v2/admin/delivery/orders/analytics/daigou"


def extract_daigou_page(body: Any) -> Tuple[List[Dict[str, Any]], int, int]:
    """Return (items, current_page, last_page)."""
    if not isinstance(body, dict):
        return [], 1, 1
    total_hint = _coerce_int(body.get("count")) or 0
    chunk = body.get("data")
    if not isinstance(chunk, dict):
        return [], 1, 1
    items = chunk.get("data")
    if not isinstance(items, list):
        items = []
    items = [x for x in items if isinstance(x, dict)]
    current = _coerce_int(chunk.get("current_page")) or 1
    last = _coerce_int(chunk.get("last_page")) or 1
    total = _coerce_int(chunk.get("total")) or total_hint or len(items)
    if total and not items:
        pass
    return items, current, last


async def fetch_daigou_orders(
    client: SahiyApiClient,
    user_id: int,
    *,
    page: int = 1,
    size: int = 10,
) -> Tuple[List[Dict[str, Any]], int]:
    body = await client.get_json(
        DAIGOU_ANALYTICS_PATH,
        params={"user_id": user_id, "page": page, "size": size},
    )
    items, _, last_page = extract_daigou_page(body)
    total = 0
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, dict):
            total = _coerce_int(data.get("total")) or _coerce_int(body.get("count")) or len(items)
        else:
            total = _coerce_int(body.get("count")) or len(items)
    return items, total


async def find_daigou_by_sn(
    client: SahiyApiClient,
    user_id: int,
    order_sn: str,
    *,
    page_size: int = 50,
    max_pages: int = 5,
) -> Optional[Dict[str, Any]]:
    target = order_sn.strip().upper()
    if not target:
        return None

    page = 1
    while page <= max_pages:
        body = await client.get_json(
            DAIGOU_ANALYTICS_PATH,
            params={"user_id": user_id, "page": page, "size": page_size},
        )
        items, _, last_page = extract_daigou_page(body)
        for row in items:
            sn = str(row.get("order_sn") or "").strip().upper()
            if sn == target:
                return row
        if page >= last_page:
            break
        page += 1

    logger.info("Daigou order_sn %s not found for user_id=%s", target, user_id)
    return None


def _coerce_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
