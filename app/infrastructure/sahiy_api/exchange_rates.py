"""CNY → UZS exchange rate from Sahiy client API."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_cache_rate: Optional[float] = None
_cache_at: float = 0.0


def parse_cny_uzs_rate(body: Any) -> Optional[float]:
    """Extract CNY→UZS rate from /api/client/exchange/rates response."""
    if not isinstance(body, dict):
        return None
    ret = body.get("ret")
    try:
        if ret is not None and int(ret) not in (1, 200):
            return None
    except (TypeError, ValueError):
        pass

    data = body.get("data")
    if not isinstance(data, list):
        return None

    for row in data:
        if not isinstance(row, dict):
            continue
        if str(row.get("from", "")).upper() != "CNY":
            continue
        if str(row.get("currency_code", "")).upper() != "UZS":
            continue
        try:
            rate = float(row.get("rate") or 0)
        except (TypeError, ValueError):
            continue
        if rate > 0:
            return rate
    return None


async def fetch_cny_uzs_rate() -> Optional[float]:
    """GET exchange rates with x-uuid header."""
    settings = get_settings()
    url = settings.sahiy_exchange_api_url.strip()
    uuid = settings.sahiy_exchange_client_uuid.strip()
    if not url or not uuid:
        return None

    headers = {"x-uuid": uuid}
    try:
        async with httpx.AsyncClient(timeout=settings.sahiy_api_timeout_seconds) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("Exchange rates HTTP %s: %s", resp.status_code, resp.text[:120])
                return None
            body = resp.json()
    except Exception as exc:
        logger.warning("Exchange rates fetch error: %s", exc)
        return None

    rate = parse_cny_uzs_rate(body)
    if rate:
        logger.info("CNY→UZS rate fetched: %s", rate)
    else:
        logger.warning("Exchange rates response missing CNY→UZS")
    return rate


async def get_cny_uzs_rate(*, ttl_seconds: Optional[int] = None) -> float:
    """Return cached CNY→UZS rate, refreshing when stale."""
    global _cache_rate, _cache_at

    settings = get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else settings.sahiy_exchange_cache_ttl_seconds
    now = time.time()

    if _cache_rate is not None and (now - _cache_at) < ttl:
        return _cache_rate

    rate = await fetch_cny_uzs_rate()
    if rate is None:
        fallback = settings.sahiy_exchange_cny_uzs_fallback
        if fallback > 0:
            logger.info("Using fallback CNY→UZS rate: %s", fallback)
            return fallback
        return settings.sahiy_exchange_cny_uzs_fallback

    _cache_rate = rate
    _cache_at = now
    return rate


def clear_exchange_rate_cache() -> None:
    global _cache_rate, _cache_at
    _cache_rate = None
    _cache_at = 0.0
