"""Authenticated HTTP client for Sahiy API (Bearer token, 401 retry)."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.infrastructure.sahiy_api.auth import ServiceUserAuth

logger = logging.getLogger(__name__)


class SahiyApiClient:
    def __init__(self, auth: ServiceUserAuth) -> None:
        self._auth = auth
        self._base_url = auth.base_url
        self._timeout = auth.timeout_seconds

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        params_list: Optional[list[tuple[str, Any]]] = None,
        json: Optional[dict[str, Any]] = None,
        retry_on_401: bool = True,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        token = await self._auth.get_access_token()
        response = await self._send(
            method, path, token, params=params, params_list=params_list, json=json, timeout=timeout
        )

        if response.status_code == 401 and retry_on_401:
            logger.info("Sahiy API 401 — refreshing service_user token and retrying %s", path)
            await self._auth.invalidate()
            token = await self._auth.get_access_token(force_refresh=True)
            response = await self._send(
                method,
                path,
                token,
                params=params,
                params_list=params_list,
                json=json,
                timeout=timeout,
            )

        return response

    async def get_json(
        self,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        params_list: Optional[list[tuple[str, Any]]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        response = await self.request(
            "GET", path, params=params, params_list=params_list, timeout=timeout
        )
        if response.status_code >= 400:
            logger.warning(
                "Sahiy API %s %s -> %s: %s",
                "GET",
                path,
                response.status_code,
                response.text[:300],
            )
            return None
        try:
            return response.json()
        except ValueError:
            logger.warning("Sahiy API invalid JSON for GET %s", path)
            return None

    async def _send(
        self,
        method: str,
        path: str,
        token: str,
        *,
        params: Optional[dict[str, Any]] = None,
        params_list: Optional[list[tuple[str, Any]]] = None,
        json: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        url = path if path.startswith("http") else f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        query: Any = params_list if params_list is not None else params
        req_timeout = timeout if timeout is not None else self._timeout
        async with httpx.AsyncClient(timeout=req_timeout) as client:
            return await client.request(
                method,
                url,
                headers=headers,
                params=query,
                json=json,
            )
