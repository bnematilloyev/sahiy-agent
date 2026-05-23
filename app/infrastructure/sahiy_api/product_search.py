"""1688 mahsulot qidiruv — client purchase search API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Optional
from urllib.parse import quote, urlencode

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SEARCH_PATH = "/api/client/purchase/search/item"

_REPLY_LANG_TO_API: dict[str, str] = {
    "uz_lat": "uz_UZ",
    "uz_cyrl": "uz_UZ",
    "ru": "ru_RU",
    "en": "en_US",
    "zh": "zh_CN",
}


@dataclass(frozen=True)
class ProductSearchItem:
    title: str
    pic_url: str
    detail_url: str
    price_cny: float
    direct_price_cny: float
    cargo_fee_cny: float
    sales: int
    num_iid: Optional[int] = None


def reply_language_to_api_header(lang: str) -> str:
    return _REPLY_LANG_TO_API.get(lang) or "uz_UZ"


def build_goods_deeplink(detail_url: str, *, base: Optional[str] = None) -> str:
    settings = get_settings()
    prefix = (base or settings.sahiy_goods_deeplink_base).strip()
    if not prefix.endswith("=") and "?" in prefix:
        return f"{prefix}{quote(detail_url, safe='')}"
    if prefix.endswith("="):
        return f"{prefix}{quote(detail_url, safe='')}"
    return f"{prefix}?u={quote(detail_url, safe='')}"


def build_product_search_deeplink(
    keyword: str,
    *,
    page_size: Optional[int] = None,
    platform: str = "1688",
    sort: Optional[str] = None,
    base: Optional[str] = None,
) -> str:
    """Ilovada to'liq qidiruv ro'yxatini ochish (keyword + page_size)."""
    settings = get_settings()
    root = (base or settings.sahiy_product_search_deeplink_base).strip().rstrip("/?")
    size = page_size if page_size is not None else settings.sahiy_product_search_see_all_page_size
    params: dict[str, str] = {
        "keyword": keyword.strip(),
        "page_size": str(max(1, int(size))),
        "platform": platform.strip() or "1688",
    }
    sort_val = (sort or settings.sahiy_product_search_sort or "").strip()
    if sort_val:
        params["sort"] = sort_val
    return f"{root}?{urlencode(params)}"


def build_category_search_deeplink(
    category: str,
    display_name: str,
    *,
    platform: str = "1688",
    base: Optional[str] = None,
) -> str:
    """Veb katalog: /search?category=皮草&displayName=…&platform=1688."""
    settings = get_settings()
    root = (base or settings.sahiy_category_search_deeplink_base).strip().rstrip("/?")
    cat = category.strip()
    if not cat:
        raise ValueError("category is required")
    params: dict[str, str] = {
        "category": cat,
        "displayName": (display_name or cat).strip(),
        "platform": platform.strip() or "1688",
    }
    return f"{root}?{urlencode(params)}"


def _parse_float(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def parse_search_response(body: Any) -> List[ProductSearchItem]:
    if not isinstance(body, dict):
        return []
    ret = body.get("ret")
    try:
        if ret is not None and int(ret) not in (1, 200):
            return []
    except (TypeError, ValueError):
        return []

    data = body.get("data")
    if not isinstance(data, dict):
        return []
    items_wrap = data.get("items")
    if not isinstance(items_wrap, dict):
        return []
    raw_items = items_wrap.get("item")
    if raw_items is None:
        return []
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        return []

    out: List[ProductSearchItem] = []
    for row in raw_items:
        if not isinstance(row, dict):
            continue
        detail = str(row.get("detail_url") or "").strip()
        pic = str(row.get("pic_url") or "").strip()
        title = str(row.get("title") or row.get("title_cn") or "").strip()
        if not detail or not pic or not title:
            continue
        num_iid = row.get("num_iid")
        try:
            num_iid_int = int(num_iid) if num_iid is not None else None
        except (TypeError, ValueError):
            num_iid_int = None
        price = _parse_float(row.get("price") or row.get("promotion_price"))
        direct = _parse_float(row.get("direct_price")) or price
        cargo = _parse_float(row.get("cargo_fee"))
        try:
            sales = int(row.get("sales") or 0)
        except (TypeError, ValueError):
            sales = 0
        out.append(
            ProductSearchItem(
                title=title,
                pic_url=pic,
                detail_url=detail,
                price_cny=price,
                direct_price_cny=direct,
                cargo_fee_cny=cargo,
                sales=sales,
                num_iid=num_iid_int,
            )
        )
    return out


async def search_products(
    keyword: str,
    lang: str,
    *,
    page: int = 1,
    page_size: int = 6,
    platform: str = "1688",
    sort: str = "asc",
) -> List[ProductSearchItem]:
    settings = get_settings()
    base = settings.sahiy_api_base_url.strip().rstrip("/")
    uuid = settings.sahiy_exchange_client_uuid.strip()
    if not base or not uuid:
        logger.warning("product search: SAHIY_API_BASE_URL or SAHIY_EXCHANGE_CLIENT_UUID missing")
        return []

    url = f"{base}{SEARCH_PATH}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-uuid": uuid,
        "language": reply_language_to_api_header(lang),
    }
    params = {
        "page": page,
        "page_size": page_size,
        "platform": platform,
        "keyword": keyword.strip(),
        "sort": sort,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.sahiy_api_timeout_seconds) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code >= 400:
                logger.warning(
                    "product search HTTP %s keyword=%r: %s",
                    resp.status_code,
                    keyword[:40],
                    resp.text[:200],
                )
                return []
            body = resp.json()
    except Exception as exc:
        logger.warning("product search failed keyword=%r: %s", keyword[:40], exc)
        return []

    items = parse_search_response(body)
    logger.info("product search keyword=%r lang=%s count=%s", keyword[:40], lang, len(items))
    return items
