"""Captcha OCR for Sahiy admin panel login (Claude vision)."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional, Tuple

import anthropic

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_CAPTCHA_PROMPT = (
    "This image is a login captcha code. "
    "Reply with ONLY the characters shown — no spaces, punctuation, or explanation."
)


def parse_data_url(data_url: str) -> Tuple[str, str]:
    """Return (media_type, base64_payload) from a data URL or raw base64."""
    if not data_url.startswith("data:"):
        return "image/png", data_url.strip()
    header, _, payload = data_url.partition(",")
    media = header.split(";")[0].removeprefix("data:").strip() or "image/png"
    return media, payload.strip()


def normalize_captcha(text: str, *, case_sensitive: bool = False) -> str:
    """Clean LLM output to captcha submit format."""
    cleaned = text.strip()
    cleaned = cleaned.splitlines()[0].strip()
    cleaned = re.sub(r'^["\'`]+|["\'`]+$', "", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned)
    if not case_sensitive:
        cleaned = cleaned.upper()
    return cleaned


async def solve_captcha_from_data_url(
    img_data_url: str,
    *,
    case_sensitive: bool = False,
) -> Optional[str]:
    """Read captcha characters from a base64 PNG/JPEG data URL."""
    settings = get_settings()
    if not settings.has_anthropic:
        logger.warning("Captcha OCR skipped: ANTHROPIC_API_KEY not configured")
        return None

    media_type, b64 = parse_data_url(img_data_url)
    if not b64:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=settings.anthropic_model,
                max_tokens=16,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64,
                                },
                            },
                            {"type": "text", "text": _CAPTCHA_PROMPT},
                        ],
                    }
                ],
            ),
            timeout=settings.ai_timeout_seconds,
        )
    except Exception as exc:
        logger.warning("Captcha OCR request failed: %s", exc)
        return None

    for block in response.content:
        if block.type == "text" and block.text.strip():
            result = normalize_captcha(block.text, case_sensitive=case_sensitive)
            if result:
                logger.info("Captcha OCR solved (%d chars)", len(result))
                return result
    logger.warning("Captcha OCR returned empty text")
    return None
