from __future__ import annotations


def is_billing_or_auth_error(exc: BaseException) -> bool:
    """True when the provider is likely out of quota, rate-limited, or misconfigured."""
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
