"""Product search use case — infrastructure behind a service boundary."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from app.core.config import Settings, get_settings
from app.infrastructure.sahiy_api.exchange_rates import get_cny_uzs_rate
from app.infrastructure.sahiy_api.product_search import ProductSearchItem, search_products
from app.services.product_search_keywords import extract_product_search_keywords

logger = logging.getLogger(__name__)


class ProductSearchStatus(str, Enum):
    TOO_SHORT = "too_short"
    NOT_CONFIGURED = "not_configured"
    EMPTY = "empty"
    ERROR = "error"
    OK = "ok"


@dataclass(frozen=True)
class ProductSearchOutcome:
    status: ProductSearchStatus
    display_keyword: str = ""
    api_keyword: str = ""
    items: tuple[ProductSearchItem, ...] = ()
    cny_to_uzs: Optional[float] = None


class ProductSearchService:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()

    async def search(self, keyword: str, reply_language: str) -> ProductSearchOutcome:
        raw = (keyword or "").strip()
        if len(raw) < 2:
            return ProductSearchOutcome(status=ProductSearchStatus.TOO_SHORT)

        base = self._settings.sahiy_api_base_url.strip()
        uuid = self._settings.sahiy_exchange_client_uuid.strip()
        if not base or not uuid:
            return ProductSearchOutcome(
                status=ProductSearchStatus.NOT_CONFIGURED,
                display_keyword=raw,
            )

        try:
            extracted = await extract_product_search_keywords(
                raw, reply_language=reply_language
            )
            api_keyword = extracted.keyword_zh.strip() or raw
            display_keyword = extracted.display_short.strip() or raw

            items = await search_products(
                api_keyword,
                reply_language,
                page_size=max(1, self._settings.sahiy_product_search_page_size),
                sort=self._settings.sahiy_product_search_sort or "asc",
            )
            if not items:
                return ProductSearchOutcome(
                    status=ProductSearchStatus.EMPTY,
                    display_keyword=display_keyword,
                )

            rate = await get_cny_uzs_rate()
            return ProductSearchOutcome(
                status=ProductSearchStatus.OK,
                display_keyword=display_keyword,
                api_keyword=api_keyword,
                items=tuple(items),
                cny_to_uzs=rate,
            )
        except Exception:
            logger.exception("product search failed keyword=%r", raw[:40])
            return ProductSearchOutcome(
                status=ProductSearchStatus.ERROR,
                display_keyword=raw,
            )
