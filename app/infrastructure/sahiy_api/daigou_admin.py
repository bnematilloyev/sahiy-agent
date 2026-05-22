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


def _parse_sku(raw: Dict[str, Any]) -> SkuInfo:
    sku_info = raw.get("sku_info") or {}
    imgs: List[str] = []
    raw_imgs = sku_info.get("imgs") or []
    if isinstance(raw_imgs, list):
        imgs = [str(u) for u in raw_imgs if u]
    sku_img = sku_info.get("sku_img")
    if sku_img and sku_img not in imgs:
        imgs.insert(0, str(sku_img))

    specs: List[Dict[str, str]] = []
    raw_specs = sku_info.get("specs") or []
    if isinstance(raw_specs, list):
        for s in raw_specs:
            if isinstance(s, dict):
                specs.append({"label": str(s.get("label", "")), "value": str(s.get("value", ""))})

    def _f(key: str) -> float:
        try:
            return float(raw.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    return SkuInfo(
        name=str(raw.get("name") or "").strip(),
        platform=str(raw.get("platform") or ""),
        platform_url=str(raw.get("platform_url") or ""),
        platform_sku=str(raw.get("platform_sku") or ""),
        quantity=int(raw.get("quantity") or 1),
        price=_f("price"),
        actual_price=_f("actual_price"),
        amount=_f("amount"),
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
        try:
            return float(raw.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    return DaigouOrderDetail(
        order_id=int(order_id),
        order_sn=str(raw.get("order_sn") or ""),
        status=int(raw.get("status") or 0),
        status_name=str(raw.get("status_name") or ""),
        goods_amount=_f("goods_amount"),
        amount=_f("amount"),
        skus=skus,
    )


async def _admin_get(path: str, *, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    settings = get_settings()
    base = settings.sahiy_api_base_url.rstrip("/")
    token = await get_admin_token()
    if not token:
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


async def fetch_daigou_order_detail(order_id: int) -> Optional[DaigouOrderDetail]:
    """GET /api/admin/daigou-orders/{id} — to'liq SKU bilan."""
    body = await _admin_get(f"/api/admin/daigou-orders/{order_id}")
    if not body:
        return None
    raw = body.get("data")
    if not isinstance(raw, dict):
        return None
    return _parse_order(raw)


async def find_daigou_detail_by_sn(
    user_id: int,
    order_sn: str,
) -> Optional[DaigouOrderDetail]:
    """Search by order_sn (prefix match), return first hit with matching SN."""
    body = await _admin_get(
        "/api/admin/daigou-orders/",
        params={"user_id": user_id, "order_sn": order_sn, "size": 5},
    )
    if not body:
        return None

    items: List[Dict[str, Any]] = []
    data = body.get("data")
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, list):
            items = inner

    target = order_sn.upper().strip()
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("order_sn", "")).upper().strip() == target:
            parsed = _parse_order(item)
            if parsed:
                # Get full detail with SKU images via /id endpoint
                detail = await fetch_daigou_order_detail(parsed.order_id)
                return detail or parsed
    return None
