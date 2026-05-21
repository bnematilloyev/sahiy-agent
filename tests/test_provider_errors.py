from __future__ import annotations

from app.core.provider_errors import is_billing_or_auth_error


class FakeRateLimitError(Exception):
    pass


def test_string_fallback_detects_quota_message():
    assert is_billing_or_auth_error(Exception("insufficient_quota exceeded"))


def test_string_fallback_detects_429():
    assert is_billing_or_auth_error(Exception("HTTP 429 rate limit"))


def test_unrelated_error_returns_false():
    assert not is_billing_or_auth_error(Exception("connection reset by peer"))


def test_openai_rate_limit_class_when_available():
    try:
        from openai import RateLimitError
    except ImportError:
        return

    exc = RateLimitError.__new__(RateLimitError)
    Exception.__init__(exc, "rate limited")
    assert is_billing_or_auth_error(exc)
