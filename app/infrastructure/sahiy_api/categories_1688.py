"""1688 kategoriyalar — client API, kunlik in-memory cache."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import get_settings
from app.infrastructure.sahiy_api.product_search import reply_language_to_api_header

logger = logging.getLogger(__name__)

CATEGORIES_PATH = "/api/client/1688-categories"

_cache: Dict[str, Tuple[List["Category1688"], float]] = {}


@dataclass(frozen=True)
class Category1688:
    id: int
    ali_category_id: int
    ali_parent_id: int
    name_cn: str
    name_en: str
    name_uz: str
    name_ru: str
    leaf: int
    level: int
    image_url: Optional[str] = None
    image: Optional[str] = None
    sort: int = 0


def category_display_name(cat: Category1688, lang: str) -> str:
    """Mijoz tiliga mos kategoriya nomi."""
    key = (lang or "uz_lat").lower()
    if key in ("ru",):
        return cat.name_ru or cat.name_uz or cat.name_en or cat.name_cn
    if key in ("en",):
        return cat.name_en or cat.name_uz or cat.name_ru or cat.name_cn
    if key in ("zh",):
        return cat.name_cn or cat.name_en or cat.name_uz
    return cat.name_uz or cat.name_ru or cat.name_en or cat.name_cn


def _normalize_parent_id(parent_id: Optional[int]) -> int:
    """API: asosiy kategoriyalar uchun parent_id=0."""
    if parent_id is None or parent_id <= 0:
        return 0
    return int(parent_id)


def _cache_key(parent_id: Optional[int]) -> str:
    if parent_id is None or parent_id <= 0:
        return "root"
    return str(int(parent_id))


def parse_categories_response(body: Any) -> List[Category1688]:
    if not isinstance(body, dict):
        return []
    ret = body.get("ret")
    try:
        if ret is not None and int(ret) not in (1, 200):
            return []
    except (TypeError, ValueError):
        return []

    data = body.get("data")
    if not isinstance(data, list):
        return []

    out: List[Category1688] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        try:
            cat_id = int(row.get("id") or 0)
            ali_id = int(row.get("ali_category_id") or 0)
            ali_parent = int(row.get("ali_parent_id") or 0)
        except (TypeError, ValueError):
            continue
        if cat_id <= 0:
            continue
        try:
            leaf = int(row.get("leaf") or 0)
            level = int(row.get("level") or 0)
            sort = int(row.get("sort") or 0)
        except (TypeError, ValueError):
            leaf, level, sort = 0, 0, 0
        image_url = str(row.get("image_url") or "").strip() or None
        image = str(row.get("image") or "").strip() or None
        out.append(
            Category1688(
                id=cat_id,
                ali_category_id=ali_id,
                ali_parent_id=ali_parent,
                name_cn=str(row.get("name_cn") or "").strip(),
                name_en=str(row.get("name_en") or "").strip(),
                name_uz=str(row.get("name_uz") or "").strip(),
                name_ru=str(row.get("name_ru") or "").strip(),
                leaf=leaf,
                level=level,
                image_url=image_url,
                image=image,
                sort=sort,
            )
        )
    out.sort(key=lambda c: (c.sort, category_display_name(c, "uz_lat")))
    return out


async def fetch_categories_1688(
    *,
    parent_id: Optional[int] = None,
    lang: str = "uz_lat",
) -> List[Category1688]:
    settings = get_settings()
    base = settings.sahiy_api_base_url.strip().rstrip("/")
    uuid = settings.sahiy_exchange_client_uuid.strip()
    if not base or not uuid:
        logger.warning("1688 categories: SAHIY_API_BASE_URL or SAHIY_EXCHANGE_CLIENT_UUID missing")
        return []

    url = f"{base}{CATEGORIES_PATH}"
    headers = {
        "Accept": "application/json",
        "x-uuid": uuid,
        "language": reply_language_to_api_header(lang),
    }
    params: Dict[str, Any] = {"parent_id": _normalize_parent_id(parent_id)}

    try:
        async with httpx.AsyncClient(timeout=settings.sahiy_api_timeout_seconds) as client:
            resp = await client.get(url, headers=headers, params=params or None)
            if resp.status_code >= 400:
                logger.warning(
                    "1688 categories HTTP %s parent_id=%s: %s",
                    resp.status_code,
                    parent_id,
                    resp.text[:200],
                )
                return []
            body = resp.json()
    except Exception as exc:
        logger.warning("1688 categories failed parent_id=%s: %s", parent_id, exc)
        return []

    items = parse_categories_response(body)
    logger.info("1688 categories parent_id=%s count=%s", parent_id, len(items))
    return items


async def get_categories_1688_cached(
    *,
    parent_id: Optional[int] = None,
    lang: str = "uz_lat",
    ttl_seconds: Optional[int] = None,
) -> List[Category1688]:
    """Kunlik cache — har parent_id uchun TTL ichida qayta so'rov yuborilmaydi."""
    settings = get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else settings.sahiy_1688_categories_cache_ttl_seconds
    key = _cache_key(parent_id)
    now = time.time()
    cached = _cache.get(key)
    if cached is not None and (now - cached[1]) < ttl:
        return cached[0]

    items = await fetch_categories_1688(parent_id=parent_id, lang=lang)
    _cache[key] = (items, now)
    logger.info("1688 categories cache refreshed key=%s count=%s", key, len(items))
    return items


def find_category_in_cache(category_id: int) -> Optional[Category1688]:
    """Oldingi so'rovlardan kategoriya (nom uchun)."""
    for items, _ts in _cache.values():
        for cat in items:
            if cat.id == category_id:
                return cat
    return None


def clear_categories_1688_cache() -> None:
    _cache.clear()
