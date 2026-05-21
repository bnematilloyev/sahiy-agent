from __future__ import annotations

import time

import httpx
import pytest

from app.core.config import Settings
from app.infrastructure.sahiy_api.auth import ServiceUserAuth
from app.infrastructure.sahiy_api.client import SahiyApiClient


@pytest.fixture
def auth_settings():
    return Settings(
        sahiy_api_base_url="https://api.test",
        service_user_phone="998901234567",
        service_user_password="secret",
        sahiy_api_timeout_seconds=5,
        service_user_token_buffer_seconds=10,
    )


def _patch_login(auth: ServiceUserAuth, transport: httpx.MockTransport) -> None:
    async def mock_login():
        async with httpx.AsyncClient(transport=transport, timeout=5) as client:
            response = await client.post(
                f"{auth.base_url}/api/v2/service/user/login/",
                json={
                    "phone": auth._phone,
                    "password": auth._password,
                    "device_id": auth._device_id,
                },
            )
            response.raise_for_status()
            return auth._parse_token_response(response.json())

    auth._login = mock_login  # type: ignore[method-assign]


def _patch_send(client: SahiyApiClient, transport: httpx.MockTransport) -> None:
    async def mock_send(method, path, token, *, params=None, json=None):
        url = f"{client._base_url}{path}"
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(transport=transport, timeout=5) as http:
            return await http.request(method, url, headers=headers, params=params, json=json)

    client._send = mock_send  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_login_caches_token_until_expiry(auth_settings):
    calls = {"login": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login/"):
            calls["login"] += 1
            return httpx.Response(200, json={"access_token": "tok-a", "expires_in": 3600})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    auth = ServiceUserAuth(auth_settings)
    _patch_login(auth, transport)

    assert await auth.get_access_token() == "tok-a"
    assert await auth.get_access_token() == "tok-a"
    assert calls["login"] == 1

    auth._cache.expires_at = time.time() - 1  # type: ignore[union-attr]
    await auth.get_access_token()
    assert calls["login"] == 2


@pytest.mark.asyncio
async def test_client_retries_once_on_401(auth_settings):
    calls = {"api": 0, "login": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login/"):
            calls["login"] += 1
            return httpx.Response(
                200,
                json={"access_token": f"tok-{calls['login']}", "expires_in": 3600},
            )
        if request.url.path == "/api/v2/admin/delivery/orders/user/42":
            calls["api"] += 1
            if calls["api"] == 1:
                return httpx.Response(401)
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    auth = ServiceUserAuth(auth_settings)
    _patch_login(auth, transport)
    client = SahiyApiClient(auth)
    _patch_send(client, transport)

    body = await client.get_json("/api/v2/admin/delivery/orders/user/42")
    assert body == {"data": []}
    assert calls["api"] == 2
    assert calls["login"] == 2
