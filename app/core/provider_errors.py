from __future__ import annotations


def is_billing_or_auth_error(exc: BaseException) -> bool:
    """True when the provider is likely out of quota, rate-limited, or misconfigured."""
    if _is_openai_billing_or_auth(exc):
        return True
    if _is_anthropic_billing_or_auth(exc):
        return True
    return _message_suggests_billing_or_auth(exc)


def _is_openai_billing_or_auth(exc: BaseException) -> bool:
    try:
        from openai import APIStatusError, AuthenticationError, RateLimitError
    except ImportError:
        return False

    if isinstance(exc, (AuthenticationError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError) and exc.status_code in (401, 403, 429):
        return True
    return False


def _is_anthropic_billing_or_auth(exc: BaseException) -> bool:
    try:
        from anthropic import APIStatusError, AuthenticationError, RateLimitError
    except ImportError:
        return False

    if isinstance(exc, (AuthenticationError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError) and exc.status_code in (401, 403, 429):
        return True
    return False


def _message_suggests_billing_or_auth(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "insufficient_quota",
            "exceeded your current quota",
            "credit balance",
            "billing",
            "rate_limit",
            "rate limit",
            "invalid_api_key",
            "authentication",
            "401",
            "403",
            "429",
        )
    )
