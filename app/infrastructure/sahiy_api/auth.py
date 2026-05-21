"""Service-user login, token cache, and refresh."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.core.config import Settings
from app.core.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

LOGIN_PATH = "/api/v2/service/user/login/"
REFRESH_PATH = "/api/v2/service/user/refresh-token/"


@dataclass
class _CachedToken:
    access_token: str
    refresh_token: Optional[str]
    expires_at: float  # unix epoch seconds


class ServiceUserAuth:
    """Caches access token until expiry; refreshes on demand or after 401."""

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.sahiy_api_base_url.rstrip("/")
        self.timeout_seconds = settings.sahiy_api_timeout_seconds
        self._phone = settings.service_user_phone.strip()
        self._password = settings.service_user_password
        self._device_id = settings.service_user_device_id.strip() or "sahiy-agent"
        self._buffer = max(0, settings.service_user_token_buffer_seconds)
        self._cache: Optional[_CachedToken] = None
        self._lock = asyncio.Lock()

    @property
    def is_configured(self) -> bool:
        return bool(self._phone and self._password and self.base_url)

    async def get_access_token(self, *, force_refresh: bool = False) -> str:
        if not self.is_configured:
            raise ConfigurationError(
                "Service user not configured (SAHIY_API_BASE_URL, SERVICE_USER_PHONE, SERVICE_USER_PASSWORD)"
            )

        async with self._lock:
            if not force_refresh and self._cache and not self._is_expired(self._cache):
                return self._cache.access_token

            if self._cache and self._cache.refresh_token and not force_refresh:
                try:
                    bundle = await self._refresh(self._cache.refresh_token)
                    self._cache = bundle
                    return bundle.access_token
                except httpx.HTTPError as exc:
                    logger.warning("Service user token refresh failed: %s", exc)

            bundle = await self._login()
            self._cache = bundle
            return bundle.access_token

    async def invalidate(self) -> None:
        async with self._lock:
            self._cache = None

    def _is_expired(self, cached: _CachedToken) -> bool:
        return time.time() >= (cached.expires_at - self._buffer)

    async def _login(self) -> _CachedToken:
        payload = {
            "phone": self._phone,
            "password": self._password,
            "device_id": self._device_id,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(f"{self.base_url}{LOGIN_PATH}", json=payload)
            response.raise_for_status()
            return self._parse_token_response(response.json())

    async def _refresh(self, refresh_token: str) -> _CachedToken:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}{REFRESH_PATH}",
                json={"refresh_token": refresh_token},
            )
            response.raise_for_status()
            return self._parse_token_response(response.json())

    def _parse_token_response(self, body: Any) -> _CachedToken:
        if not isinstance(body, dict):
            raise ValueError("Token response must be a JSON object")

        data = body.get("data") if isinstance(body.get("data"), dict) else body
        access = (
            data.get("access_token")
            or data.get("token")
            or body.get("access_token")
            or body.get("token")
        )
        if not access or not isinstance(access, str):
            raise ValueError("Token response missing access_token/token")

        refresh = data.get("refresh_token") or body.get("refresh_token")
        if refresh is not None and not isinstance(refresh, str):
            refresh = None

        expires_in = (
            data.get("expires_in")
            or data.get("expiresIn")
            or body.get("expires_in")
            or body.get("expiresIn")
        )
        if expires_in is None:
            expires_in = 3600
        try:
            ttl = int(expires_in)
        except (TypeError, ValueError):
            ttl = 3600

        return _CachedToken(
            access_token=access,
            refresh_token=refresh,
            expires_at=time.time() + ttl,
        )
