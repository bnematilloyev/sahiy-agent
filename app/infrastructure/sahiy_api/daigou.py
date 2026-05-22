"""Daigou orders — Xitoy omborigacha (analytics API)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.infrastructure.sahiy_api.client import SahiyApiClient

logger = logging.getLogger(__name__)

# Admin analytics endpoint (original)
DAIGOU_ANALYTICS_PATH = "/api/v2/admin/delivery/orders/analytics/daigou"
# Custom endpoint with status[] filter support
CUSTOM_DAIGOU_PATH = "/api/custom-daigou-orders/"

# Intent → daigou status kodi(lar)
# docs: 0=To'lov kutilmoqda, 1=To'langan, 2=Sotib olinmoqda, 3=Sotib olindi,
#       4=Sklatga kutilmoqda, 5=Sklatda, 6=Yo'lda/Yakunlangan,
#       10=Bekor qilingan, 11=O'chirilgan, 12=Xatolik
_INTENT_STATUS_MAP: Dict[str, List[int]] = {
    "active":    [1, 2, 3, 4, 5, 6],          # to'langan + jarayondagi barcha
    "cancelled": [10, 11],
    "completed": [6],
    "in_china":  [0, 1, 2, 3, 4, 5, 6],       # Xitoyda bo'lganlar
}


def intent_status_codes(row_filter: Optional[str]) -> Optional[List[int]]:
    """Intent asosida API ga beradigan status ro'yxati."""
    if not row_filter:
        return None
    return _INTENT_STATUS_MAP.get(row_filter)


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
    return items, current, last


def _extract_custom_page(body: Any) -> Tuple[List[Dict[str, Any]], int, int]:
    """Parse /api/custom-daigou-orders/ response."""
    if not isinstance(body, dict):
        return [], 1, 1
    # Try analytics-style first
    chunk = body.get("data")
    if isinstance(chunk, dict) and "data" in chunk:
        return extract_daigou_page(body)
    # Flat list style
    if isinstance(chunk, list):
        items = [x for x in chunk if isinstance(x, dict)]
        return items, 1, 1
    if isinstance(body.get("orders"), list):
        items = [x for x in body["orders"] if isinstance(x, dict)]
        return items, 1, 1
    # Try nested pagination
    for key in ("data", "result", "items"):
        val = body.get(key)
        if isinstance(val, list):
            items = [x for x in val if isinstance(x, dict)]
            return items, 1, 1
        if isinstance(val, dict):
            inner = val.get("data")
            if isinstance(inner, list):
                items = [x for x in inner if isinstance(x, dict)]
                current = _coerce_int(val.get("current_page")) or 1
                last = _coerce_int(val.get("last_page")) or 1
                return items, current, last
    return [], 1, 1


async def fetch_daigou_orders(
    client: SahiyApiClient,
    user_id: int,
    *,
    page: int = 1,
    size: int = 10,
    status_codes: Optional[Sequence[int]] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Daigou buyurtmalarini olish.

    status_codes berilsa → /api/custom-daigou-orders/?status[]=... bilan server filtr.
    Berilmasa → analytics endpoint (barcha statuslar).
    """
    if status_codes is not None:
        return await _fetch_custom(client, user_id, page=page, size=size, status_codes=list(status_codes))

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


async def _fetch_custom(
    client: SahiyApiClient,
    user_id: int,
    *,
    page: int = 1,
    size: int = 10,
    status_codes: List[int],
) -> Tuple[List[Dict[str, Any]], int]:
    """
    /api/custom-daigou-orders/ endpoint — status[] filter bilan.
    Laravel: status[]=1&status[]=2&...
    """
    params_list = [
        ("user_id", user_id),
        ("page", page),
        ("size", size),
    ]
    for code in status_codes:
        params_list.append(("status[]", code))

    try:
        body = await client.get_json(CUSTOM_DAIGOU_PATH, params_list=params_list)
    except Exception as exc:
        logger.warning(
            "custom-daigou-orders failed (status=%s): %s — analytics fallbackga o'tish",
            status_codes,
            exc,
        )
        # Fallback: analytics endpoint, client-side filter keyinroq qilinadi
        body = await client.get_json(
            DAIGOU_ANALYTICS_PATH,
            params={"user_id": user_id, "page": page, "size": size},
        )
        items, _, _ = extract_daigou_page(body)
        total = _coerce_int(body.get("data", {}).get("total") if isinstance(body.get("data"), dict) else None) or len(items)
        return items, total

    items, _, _ = _extract_custom_page(body)
    total = 0
    if isinstance(body, dict):
        for key in ("total", "count"):
            t = _coerce_int(body.get(key))
            if t is not None:
                total = t
                break
        if not total:
            data = body.get("data")
            if isinstance(data, dict):
                total = _coerce_int(data.get("total")) or len(items)
            else:
                total = len(items)
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
