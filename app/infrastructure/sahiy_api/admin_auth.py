"""Admin panel token management.

Flow:
  1. Try POST /api/admin/v1/token  (no captcha — admin_api account)
  2. If that fails, fall back to:
     GET /api/admin/captcha → POST /api/admin/login

Token is cached in-process; refreshed automatically before expiry.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()
_token: Optional[str] = None
_token_expires_at: float = 0.0


async def get_admin_token() -> Optional[str]:
    """Return a valid admin Bearer token, refreshing if needed."""
    global _token, _token_expires_at

    settings = get_settings()
    if not settings.has_admin_api:
        return None

    async with _lock:
        if _token and time.monotonic() < _token_expires_at:
            return _token

        token = await _fetch_token(settings)
        if token:
            _token = token
            _token_expires_at = time.monotonic() + settings.sahiy_admin_token_ttl_seconds
            logger.info("Admin token refreshed, valid for %ds", settings.sahiy_admin_token_ttl_seconds)
        else:
            _token = None
            _token_expires_at = 0.0
        return _token


def invalidate_admin_token() -> None:
    """Force token refresh on next call (e.g. after 401)."""
    global _token, _token_expires_at
    _token = None
    _token_expires_at = 0.0


async def _fetch_token(settings) -> Optional[str]:
    base = settings.sahiy_api_base_url.rstrip("/")
    timeout = settings.sahiy_api_timeout_seconds

    # Option 1: Open API token (no captcha) — for admin_api accounts
    token = await _open_api_token(base, settings.sahiy_admin_username, settings.sahiy_admin_password, timeout)
    if token:
        return token

    # Option 2: Panel login with captcha
    token = await _panel_login_token(base, settings.sahiy_admin_username, settings.sahiy_admin_password, timeout)
    return token


async def _open_api_token(base: str, username: str, password: str, timeout: int) -> Optional[str]:
    url = f"{base}/api/admin/v1/token"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                json={"username": username, "password": password},
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                body = resp.json()
                token = (
                    body.get("data", {}).get("access_token")
                    or body.get("access_token")
                )
                if token:
                    logger.debug("Admin token via open-api (no captcha)")
                    return str(token)
            logger.debug("Open API token failed status=%s", resp.status_code)
    except httpx.HTTPError as exc:
        logger.debug("Open API token error: %s", exc)
    return None


async def _panel_login_token(base: str, username: str, password: str, timeout: int) -> Optional[str]:
    """Full captcha → login flow."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Step 1: get captcha key
            cap_resp = await client.get(f"{base}/api/admin/captcha")
            if cap_resp.status_code != 200:
                logger.warning("Admin captcha fetch failed: %s", cap_resp.status_code)
                return None
            cap_data = cap_resp.json().get("data", {}).get("captcha", {})
            cap_key = cap_data.get("key", "")
            # Captcha is an image — for API-type accounts "1234" is accepted
            # Real captcha bypass is not supported; admin_api account is preferred
            cap_code = "1234"

            # Step 2: login
            login_resp = await client.post(
                f"{base}/api/admin/login",
                json={
                    "username": username,
                    "password": password,
                    "key": cap_key,
                    "captcha": cap_code,
                },
                headers={"Content-Type": "application/json"},
            )
            if login_resp.status_code == 200:
                body = login_resp.json()
                token = body.get("data", {}).get("access_token")
                if token:
                    logger.debug("Admin token via panel login")
                    return str(token)
            logger.warning("Admin panel login failed: %s %s", login_resp.status_code, login_resp.text[:200])
    except httpx.HTTPError as exc:
        logger.warning("Admin panel login error: %s", exc)
    return None
