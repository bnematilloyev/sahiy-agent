"""Pickup points (filial + postomat) — admin API with in-memory cache."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from app.infrastructure.sahiy_api.client import SahiyApiClient

logger = logging.getLogger(__name__)

PICKUP_POINTS_PATH = "/api/admin/pickup-points/"

_cache_points: Optional[List[Dict[str, Any]]] = None
_cache_at: float = 0.0


def _uz_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("uz", "ru", "en"):
            text = value.get(key)
            if text and str(text).strip():
                return str(text).strip()
        return ""
    return str(value).strip() if value else ""


def normalize_pickup_point(row: Dict[str, Any]) -> Dict[str, Any]:
    ptype = row.get("type")
    try:
        ptype_int = int(ptype) if ptype is not None else 0
    except (TypeError, ValueError):
        ptype_int = 0
    type_label = str(row.get("type_name") or ("Filial" if ptype_int == 1 else "Postomat")).strip()
    return {
        "id": row.get("id"),
        "name": _uz_text(row.get("name")),
        "address": _uz_text(row.get("address")),
        "phone": str(row.get("phone") or "").strip(),
        "type": ptype_int,
        "type_label": type_label,
        "region_id": row.get("region_id"),
        "region_name": str(row.get("region_name") or "").strip(),
        "city_name": str(row.get("city_name") or "").strip(),
    }


async def fetch_all_pickup_points(
    client: SahiyApiClient,
    *,
    per_page: int = 100,
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    page = 1
    while page <= max_pages:
        body = await client.get_json(PICKUP_POINTS_PATH, params={"page": page, "per_page": per_page})
        if not body:
            break
        chunk = body.get("data")
        if not isinstance(chunk, list) or not chunk:
            break
        for row in chunk:
            if isinstance(row, dict):
                items.append(normalize_pickup_point(row))
        meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
        last_page = int(meta.get("last_page") or page)
        if page >= last_page:
            break
        page += 1
    return items


async def get_pickup_points_cached(
    client: SahiyApiClient,
    *,
    ttl_seconds: int = 3600,
) -> List[Dict[str, Any]]:
    global _cache_points, _cache_at
    now = time.time()
    if _cache_points is not None and (now - _cache_at) < ttl_seconds:
        return _cache_points

    points = await fetch_all_pickup_points(client)
    _cache_points = points
    _cache_at = now
    logger.info("Pickup points cache refreshed: %s items", len(points))
    return points


def clear_pickup_points_cache() -> None:
    global _cache_points, _cache_at
    _cache_points = None
    _cache_at = 0.0
