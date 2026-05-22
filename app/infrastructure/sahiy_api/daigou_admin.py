"""Daigou order detail fetcher via admin API (SKU + images).

Uses Bearer token from admin_auth.get_admin_token().
Endpoints:
  GET /api/admin/daigou-orders/{id}           — single order (full SKU)
  GET /api/admin/daigou-orders/?user_id=&order_sn=  — search by SN
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.infrastructure.sahiy_api.admin_auth import get_admin_token, invalidate_admin_token

logger = logging.getLogger(__name__)


@dataclass
class SkuInfo:
    name: str
    platform: str
    platform_url: str
    platform_sku: str
    quantity: int
    price: float          # ÷100 qilingan
    actual_price: float
    amount: float
    specs: List[Dict[str, str]] = field(default_factory=list)
    images: List[str] = field(default_factory=list)

    @property
    def spec_label(self) -> str:
        if not self.specs:
            return ""
        return ", ".join(
            f"{s.get('label', '')}: {s.get('value', '')}"
            for s in self.specs
            if s.get("label") or s.get("value")
        )

    @property
    def thumb_url(self) -> Optional[str]:
        return self.images[0] if self.images else None


@dataclass
class DaigouOrderDetail:
    order_id: int
    order_sn: str
    status: int
    status_name: str
    goods_amount: float
    amount: float
    skus: List[SkuInfo] = field(default_factory=list)


def _money(value: Any) -> float:
    """API price fields are in fen — divide by 100 for display."""
    try:
        raw = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if raw == 0:
        return 0.0
    # Already decimal (e.g. 22.50) vs integer fen (2250)
    if abs(raw) >= 100 and raw == int(raw):
        return raw / 100.0
    return raw


def _parse_sku(raw: Dict[str, Any]) -> SkuInfo:
    sku_info = raw.get("sku_info") if isinstance(raw.get("sku_info"), dict) else {}
    imgs: List[str] = []
    raw_imgs = sku_info.get("imgs") or raw.get("imgs") or []
    if isinstance(raw_imgs, list):
        imgs = [str(u) for u in raw_imgs if u]
    sku_img = sku_info.get("sku_img") or raw.get("sku_img") or raw.get("image") or raw.get("thumb")
    if sku_img and sku_img not in imgs:
        imgs.insert(0, str(sku_img))

    specs: List[Dict[str, str]] = []
    raw_specs = sku_info.get("specs") or raw.get("specs") or []
    if isinstance(raw_specs, list):
        for s in raw_specs:
            if isinstance(s, dict):
                specs.append({"label": str(s.get("label", "")), "value": str(s.get("value", ""))})

    name = str(raw.get("name") or sku_info.get("name") or "").strip()

    quantity = int(raw.get("quantity") or 1)
    price = _money(raw.get("price"))
    actual_price = _money(raw.get("actual_price"))
    if actual_price <= 0:
        actual_price = price
    amount = _money(raw.get("amount"))
    if amount <= 0 and actual_price > 0:
        amount = actual_price * quantity

    return SkuInfo(
        name=name,
        platform=str(raw.get("platform") or ""),
        platform_url=str(raw.get("platform_url") or ""),
        platform_sku=str(raw.get("platform_sku") or ""),
        quantity=quantity,
        price=price,
        actual_price=actual_price,
        amount=amount,
        specs=specs,
        images=imgs,
    )


def _parse_order(raw: Dict[str, Any]) -> Optional[DaigouOrderDetail]:
    order_id = raw.get("id")
    if not order_id:
        return None
    skus_raw = raw.get("skus") or []
    skus = [_parse_sku(s) for s in skus_raw if isinstance(s, dict)]

    def _f(key: str) -> float:
        return _money(raw.get(key))

    return DaigouOrderDetail(
        order_id=int(order_id),
        order_sn=str(raw.get("order_sn") or ""),
        status=int(raw.get("status") or 0),
        status_name=str(raw.get("status_name") or ""),
        goods_amount=_f("goods_amount"),
        amount=_f("amount"),
        skus=skus,
    )


def parse_detail_from_row(row: Dict[str, Any]) -> Optional[DaigouOrderDetail]:
    """Parse SKU from order row already fetched (analytics/custom API fallback)."""
    if not row.get("id") and not row.get("order_sn"):
        return None
    skus_raw = row.get("skus") or []
    if not skus_raw:
        return None
    return _parse_order(row)


async def _admin_get(path: str, *, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    settings = get_settings()
    base = settings.sahiy_api_base_url.rstrip("/")
    token = await get_admin_token()
    if not token:
        logger.debug("Admin GET %s skipped — no token", path)
        return None

    url = f"{base}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=settings.sahiy_api_timeout_seconds) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 401:
                invalidate_admin_token()
                logger.warning("Admin token expired (401), invalidated")
                return None
            if resp.status_code != 200:
                logger.debug("Admin GET %s → %s", path, resp.status_code)
                return None
            return resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Admin API error %s: %s", path, exc)
        return None


def _extract_items(body: Any) -> List[Dict[str, Any]]:
    """Extract list of order dicts from any admin API response shape."""
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
        # Single object wrapped in data
        return [data]
    # Try common keys
    for key in ("orders", "items", "result"):
        val = body.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
    return []


def _extract_single(body: Any) -> Optional[Dict[str, Any]]:
    """Extract a single order dict from admin API detail response."""
    if isinstance(body, list):
        items = [x for x in body if isinstance(x, dict)]
        return items[0] if items else None
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        items = [x for x in data if isinstance(x, dict)]
        return items[0] if items else None
    # Response itself might be the order (no wrapper)
    if body.get("id") or body.get("order_sn"):
        return body
    return None


async def fetch_daigou_order_detail(order_id: int) -> Optional[DaigouOrderDetail]:
    """GET /api/admin/daigou-orders/{id} — to'liq SKU bilan."""
    body = await _admin_get(f"/api/admin/daigou-orders/{order_id}")
    if body is None:
        return None
    raw = _extract_single(body)
    if not raw:
        return None
    return _parse_order(raw)


async def find_daigou_detail_by_sn(
    user_id: int,
    order_sn: str,
) -> Optional[DaigouOrderDetail]:
    """Search by order_sn, return first hit with matching SN."""
    body = await _admin_get(
        "/api/admin/daigou-orders/",
        params={"user_id": user_id, "order_sn": order_sn, "size": 5},
    )
    if body is None:
        return None

    items = _extract_items(body)
    target = order_sn.upper().strip()
    for item in items:
        if str(item.get("order_sn", "")).upper().strip() == target:
            parsed = _parse_order(item)
            if parsed:
                # Try to get richer detail (with images) via ID endpoint
                try:
                    detail = await fetch_daigou_order_detail(parsed.order_id)
                    if detail:
                        return detail
                except Exception:
                    pass
                return parsed
    return None
