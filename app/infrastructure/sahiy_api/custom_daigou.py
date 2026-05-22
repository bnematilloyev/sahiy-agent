"""custom-daigou-orders (service_user) — SKU va express_num bo'yicha qidiruv."""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.config import get_settings
from app.domain.order_refs import is_daigou_sn
from app.infrastructure.sahiy_api.client import SahiyApiClient
from app.infrastructure.sahiy_api.daigou_admin import DaigouOrderDetail, parse_detail_from_row

logger = logging.getLogger(__name__)

CUSTOM_DAIGOU_PATH = "/api/custom-daigou-orders/"


def extract_custom_daigou_page(body: Any) -> tuple[list[dict[str, Any]], int, int, int]:
    """Return (items, current_page, last_page, total) from paginated custom-daigou response."""
    if not isinstance(body, dict):
        return [], 1, 1, 0
    data = body.get("data")
    if not isinstance(data, list):
        return [], 1, 1, 0
    items = [x for x in data if isinstance(x, dict)]
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    current = int(meta.get("current_page") or 1)
    last = int(meta.get("last_page") or 1)
    total = int(meta.get("total") or len(items))
    return items, current, last, total


def _row_matches_track(row: dict[str, Any], track: str) -> bool:
    track_norm = track.strip().upper()
    if not track_norm:
        return False
    order_sn = str(row.get("order_sn") or "").strip().upper()
    if order_sn == track_norm:
        return True
    for pkg in row.get("purchase_packages") or []:
        if not isinstance(pkg, dict):
            continue
        if str(pkg.get("express_num") or "").strip() == track.strip():
            return True
    for ex in row.get("expresses") or []:
        if not isinstance(ex, dict):
            continue
        pivot = ex.get("pivot") if isinstance(ex.get("pivot"), dict) else {}
        if str(pivot.get("express_num") or "").strip() == track.strip():
            return True
    express = row.get("express")
    if isinstance(express, dict):
        if str(express.get("express_num") or "").strip() == track.strip():
            return True
    return False


async def _fetch_page(
    client: SahiyApiClient,
    *,
    user_id: int,
    page: int = 1,
    express_num: str = "",
    order_sn: str = "",
    timeout: float,
) -> tuple[list[dict[str, Any]], int, int, int]:
    params: dict[str, Any] = {"user_id": user_id, "page": page}
    if express_num:
        params["express_num"] = express_num
    if order_sn:
        params["order_sn"] = order_sn
    body = await client.get_json(CUSTOM_DAIGOU_PATH, params=params, timeout=timeout)
    return extract_custom_daigou_page(body)


async def find_daigou_row_by_express_num(
    client: SahiyApiClient,
    user_id: int,
    express_num: str,
    *,
    timeout: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    settings = get_settings()
    req_timeout = float(timeout if timeout is not None else settings.sahiy_custom_daigou_timeout_seconds)
    items, _, _, _ = await _fetch_page(
        client,
        user_id=user_id,
        express_num=express_num.strip(),
        timeout=req_timeout,
    )
    if items:
        return items[0]
    return None


async def find_daigou_row_by_sn(
    client: SahiyApiClient,
    user_id: int,
    order_sn: str,
    *,
    timeout: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    settings = get_settings()
    req_timeout = float(timeout if timeout is not None else settings.sahiy_custom_daigou_timeout_seconds)
    items, _, _, _ = await _fetch_page(
        client,
        user_id=user_id,
        order_sn=order_sn.strip().upper(),
        timeout=req_timeout,
    )
    if items:
        return items[0]
    return None


async def scan_daigou_pages_for_track(
    client: SahiyApiClient,
    user_id: int,
    track: str,
    *,
    timeout: Optional[float] = None,
    max_pages: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """Paginated fallback when direct express_num filter returns empty."""
    settings = get_settings()
    req_timeout = float(timeout if timeout is not None else settings.sahiy_custom_daigou_timeout_seconds)
    page_limit = max_pages if max_pages is not None else settings.sahiy_custom_daigou_max_pages
    track = track.strip()
    if not track:
        return None

    items, _, last_page, _ = await _fetch_page(
        client, user_id=user_id, page=1, timeout=req_timeout
    )
    for row in items:
        if _row_matches_track(row, track):
            return row

    last = min(last_page, page_limit)
    for page in range(2, last + 1):
        items, _, _, _ = await _fetch_page(
            client, user_id=user_id, page=page, timeout=req_timeout
        )
        for row in items:
            if _row_matches_track(row, track):
                return row
    return None


async def resolve_daigou_detail(
    client: SahiyApiClient,
    user_id: int,
    *,
    track: Optional[str] = None,
    order_sn: Optional[str] = None,
) -> Optional[DaigouOrderDetail]:
    """
    Smart lookup via custom-daigou-orders:
    1. express_num (non-DG tracks)
    2. order_sn (DG…)
    3. paginated scan by user_id
    """
    settings = get_settings()
    timeout = float(settings.sahiy_custom_daigou_timeout_seconds)
    track = (track or "").strip()
    sn = (order_sn or "").strip().upper()

    row: Optional[dict[str, Any]] = None

    if track and not is_daigou_sn(track):
        row = await find_daigou_row_by_express_num(client, user_id, track, timeout=timeout)
        if row:
            logger.info("custom-daigou express_num hit user=%s track=%s", user_id, track)

    if row is None and sn and is_daigou_sn(sn):
        row = await find_daigou_row_by_sn(client, user_id, sn, timeout=timeout)
        if row:
            logger.info("custom-daigou order_sn hit user=%s sn=%s", user_id, sn)

    if row is None and track:
        row = await scan_daigou_pages_for_track(client, user_id, track, timeout=timeout)
        if row:
            logger.info("custom-daigou paginated hit user=%s track=%s", user_id, track)

    if row is None:
        return None
    return parse_detail_from_row(row)
