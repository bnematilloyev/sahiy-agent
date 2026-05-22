"""Tests for admin captcha OCR and panel login flow."""

from unittest.mock import AsyncMock, patch

import pytest

from app.infrastructure.sahiy_api.admin_auth import (
    _extract_token,
    _parse_captcha,
    _panel_login_token,
)
from app.infrastructure.sahiy_api.captcha_solver import (
    _pick_best_candidate,
    normalize_captcha,
    parse_data_url,
)


def test_parse_captcha_payload():
    body = {
        "ret": 1,
        "data": {
            "captcha": {
                "sensitive": False,
                "key": "abc-key",
                "img": "data:image/png;base64,AAA",
            }
        },
    }
    key, img, sensitive = _parse_captcha(body)
    assert key == "abc-key"
    assert img == "data:image/png;base64,AAA"
    assert sensitive is False


def test_pick_best_candidate_prefers_four_chars():
    assert _pick_best_candidate(["AB12", "AB123", "AB12"]) == "AB12"


def test_parse_data_url():
    media, b64 = parse_data_url("data:image/png;base64,QUJD")
    assert media == "image/png"
    assert b64 == "QUJD"


def test_normalize_captcha_homoglyphs():
    assert normalize_captcha("4ZXΜ", case_sensitive=False) == "4ZXM"


def test_normalize_captcha_case_insensitive():
    assert normalize_captcha('  "ab12"  \nextra', case_sensitive=False) == "AB12"


@pytest.mark.asyncio
async def test_panel_login_success_on_second_attempt():
    captcha_body = {
        "ret": 1,
        "data": {"captcha": {"key": "k1", "img": "data:image/png;base64,x", "sensitive": False}},
    }
    fail_login = {"ret": 0, "msg": "验证码错误", "data": []}
    ok_login = {"ret": 1, "msg": "ok", "data": {"access_token": "eyJtoken", "token_type": "bearer"}}

    class FakeResponse:
        def __init__(self, status_code: int, body: dict, text: str = ""):
            self.status_code = status_code
            self._body = body
            self.text = text or str(body)

        def json(self):
            return self._body

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.get = AsyncMock(return_value=FakeResponse(200, captcha_body))
            self.post = AsyncMock(
                side_effect=[
                    FakeResponse(200, fail_login),
                    FakeResponse(200, ok_login),
                ]
            )

    with patch("app.infrastructure.sahiy_api.admin_auth.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value = FakeClient()
        with patch(
            "app.infrastructure.sahiy_api.captcha_solver.solve_captcha_from_data_url",
            new=AsyncMock(side_effect=["WRONG", "1234"]),
        ):
            token = await _panel_login_token(
                "https://api.test",
                "admin",
                "pass",
                5,
                max_attempts=3,
            )

    assert token == "eyJtoken"
    assert _extract_token(ok_login) == "eyJtoken"
