"""Admin panel token management.

Priority:
  1. SAHIY_ADMIN_ACCESS_TOKEN from .env (panel JWT — no captcha)
  2. POST /api/admin/v1/token (admin_api account — no captcha)
  3. GET captcha → Claude OCR → POST /api/admin/login (panel account)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()
_token: Optional[str] = None
_token_expires_at: float = 0.0
_static_token: Optional[str] = None


def _is_success(body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    ret = body.get("ret")
    if ret is None:
        return True
    try:
        return int(ret) in (1, 200)
    except (TypeError, ValueError):
        return False


def _extract_token(body: Any) -> Optional[str]:
    """Try multiple response shapes to find access_token."""
    if not isinstance(body, dict):
        return None
    if not _is_success(body):
        return None
    data = body.get("data")
    if isinstance(data, dict):
        t = data.get("access_token") or data.get("token")
        if t:
            return str(t).strip()
    if isinstance(data, str) and data.startswith("eyJ"):
        return data.strip()
    t = body.get("access_token") or body.get("token")
    if t:
        return str(t).strip()
    return None


async def get_admin_token() -> Optional[str]:
    """Return a valid admin Bearer token, refreshing if needed."""
    global _token, _token_expires_at, _static_token

    settings = get_settings()
    if not settings.has_admin_api:
        return None

    # Static token from .env — highest priority, no auto-refresh
    env_token = (settings.sahiy_admin_access_token or "").strip()
    if env_token:
        return env_token

    async with _lock:
        if _token and time.monotonic() < _token_expires_at:
            return _token

        try:
            token = await _fetch_token(settings)
        except Exception as exc:
            logger.warning("Admin token fetch error: %s", exc)
            token = None

        if token:
            _token = token
            _token_expires_at = time.monotonic() + settings.sahiy_admin_token_ttl_seconds
            logger.info("Admin token refreshed, valid for %ds", settings.sahiy_admin_token_ttl_seconds)
        else:
            _token = None
            _token_expires_at = 0.0
        return _token


def invalidate_admin_token() -> None:
    """Force token refresh on next call (e.g. after 401). Skipped for .env token."""
    global _token, _token_expires_at
    settings = get_settings()
    if settings.sahiy_admin_access_token.strip():
        logger.warning(
            "Admin API returned 401 — SAHIY_ADMIN_ACCESS_TOKEN expired. "
            "Get a new token from panel and update .env"
        )
        return
    _token = None
    _token_expires_at = 0.0


def _parse_captcha(body: Any) -> tuple[Optional[str], Optional[str], bool]:
    """Return (key, img_data_url, case_sensitive) from GET /api/admin/captcha."""
    if not _is_success(body):
        return None, None, False
    data = body.get("data") if isinstance(body, dict) else None
    captcha = data.get("captcha") if isinstance(data, dict) else None
    if not isinstance(captcha, dict):
        return None, None, False
    key = captcha.get("key")
    img = captcha.get("img")
    sensitive = bool(captcha.get("sensitive"))
    if not key or not img:
        return None, None, sensitive
    return str(key), str(img), sensitive


async def _fetch_token(settings) -> Optional[str]:
    base = settings.sahiy_api_base_url.rstrip("/")
    timeout = settings.sahiy_api_timeout_seconds
    username = settings.sahiy_admin_username.strip()
    password = settings.sahiy_admin_password

    if not username or not password:
        return None

    token = await _open_api_token(base, username, password, timeout)
    if token:
        return token

    token = await _panel_login_token(
        base,
        username,
        password,
        timeout,
        max_attempts=settings.sahiy_admin_captcha_max_attempts,
    )
    if token:
        return token

    logger.warning(
        "Admin token not obtained. Options: SAHIY_ADMIN_ACCESS_TOKEN, "
        "admin_api via /api/admin/v1/token, or panel login with ANTHROPIC_API_KEY for captcha OCR."
    )
    return None


async def _panel_login_token(
    base: str,
    username: str,
    password: str,
    timeout: int,
    *,
    max_attempts: int = 3,
) -> Optional[str]:
    """GET captcha → Claude OCR → POST /api/admin/login."""
    from app.infrastructure.sahiy_api.captcha_solver import solve_captcha_from_data_url

    if max_attempts < 1:
        return None

    captcha_url = f"{base}/api/admin/captcha"
    login_url = f"{base}/api/admin/login"

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                cap_resp = await client.get(captcha_url)
                cap_body: Any = {}
                try:
                    cap_body = cap_resp.json()
                except Exception:
                    pass

                if cap_resp.status_code != 200:
                    logger.warning(
                        "Admin captcha HTTP %s: %s",
                        cap_resp.status_code,
                        cap_resp.text[:120],
                    )
                    continue

                key, img, case_sensitive = _parse_captcha(cap_body)
                if not key or not img:
                    logger.warning("Admin captcha response missing key/img (attempt %d)", attempt)
                    continue

                captcha_text = await solve_captcha_from_data_url(img, case_sensitive=case_sensitive)
                if not captcha_text:
                    logger.warning("Captcha OCR empty (attempt %d)", attempt)
                    continue

                login_resp = await client.post(
                    login_url,
                    json={
                        "username": username,
                        "password": password,
                        "key": key,
                        "captcha": captcha_text,
                    },
                    headers={"Content-Type": "application/json"},
                )
                login_body: Any = {}
                try:
                    login_body = login_resp.json()
                except Exception:
                    pass

                token = _extract_token(login_body)
                if token:
                    logger.info("Admin token obtained via panel login (captcha attempt %d)", attempt)
                    return token

                msg = login_body.get("msg") if isinstance(login_body, dict) else login_resp.text[:120]
                logger.warning(
                    "Admin panel login attempt %d failed: HTTP %s ret=%s msg=%s captcha=%s",
                    attempt,
                    login_resp.status_code,
                    login_body.get("ret") if isinstance(login_body, dict) else "?",
                    msg,
                    captcha_text,
                )
            except httpx.HTTPError as exc:
                logger.warning("Admin panel login attempt %d HTTP error: %s", attempt, exc)
            except Exception as exc:
                logger.warning("Admin panel login attempt %d error: %s", attempt, exc)

    return None


async def _open_api_token(base: str, username: str, password: str, timeout: int) -> Optional[str]:
    url = f"{base}/api/admin/v1/token"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                json={"username": username, "password": password},
                headers={"Content-Type": "application/json"},
            )
            body: Any = {}
            try:
                body = resp.json()
            except Exception:
                pass

            if resp.status_code == 200:
                token = _extract_token(body)
                if token:
                    logger.info("Admin token obtained via /api/admin/v1/token")
                    return token
                msg = body.get("msg") if isinstance(body, dict) else resp.text[:120]
                logger.warning("Admin v1/token HTTP 200 but no token: ret=%s msg=%s", body.get("ret") if isinstance(body, dict) else "?", msg)
            else:
                logger.warning("Admin v1/token failed HTTP %s: %s", resp.status_code, resp.text[:120])
    except Exception as exc:
        logger.warning("Admin v1/token error: %s", exc)
    return None
