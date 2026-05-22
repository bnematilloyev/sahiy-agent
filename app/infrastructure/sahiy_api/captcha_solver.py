"""Captcha OCR for Sahiy admin panel login (Claude vision)."""

from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from typing import List, Optional, Tuple

import anthropic

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Sahiy panel captcha is typically 4 alphanumeric chars (see API docs example "1234").
_CAPTCHA_LEN = 4

_PROMPT_PRIMARY = (
    "This image is a login CAPTCHA with exactly 4 characters "
    "(uppercase Latin letters A-Z and/or digits 0-9). "
    "Characters may be tilted, colored, or on a noisy background. "
    "Read left to right. Reply with ONLY those 4 characters — no spaces or punctuation."
)

_PROMPT_RETRY = (
    "CAPTCHA image: exactly 4 alphanumeric characters, left to right. "
    "Ignore lines and background noise. Output only 4 characters."
)

# Greek / Cyrillic lookalikes → Latin (common vision model mistakes).
_HOMOGLYPHS = str.maketrans(
    {
        "Α": "A",
        "Β": "B",
        "Ε": "E",
        "Ζ": "Z",
        "Η": "H",
        "Ι": "I",
        "Κ": "K",
        "Μ": "M",
        "Ν": "N",
        "Ο": "O",
        "Ρ": "P",
        "Τ": "T",
        "Υ": "Y",
        "Χ": "X",
        "α": "A",
        "β": "B",
        "ε": "E",
        "ο": "O",
        "ρ": "P",
        "χ": "X",
        "О": "O",
        "о": "O",
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "Х": "X",
    }
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
    cleaned = cleaned.translate(_HOMOGLYPHS)
    cleaned = re.sub(r"[^A-Za-z0-9]", "", cleaned)
    if not case_sensitive:
        cleaned = cleaned.upper()
    return cleaned


def _pick_best_candidate(candidates: List[str]) -> Optional[str]:
    """Prefer 4-char results; break ties by vote count."""
    if not candidates:
        return None
    four = [c for c in candidates if len(c) == _CAPTCHA_LEN]
    pool = four or candidates
    best, votes = Counter(pool).most_common(1)[0]
    logger.info(
        "Captcha OCR consensus: %r (len=%d, votes=%d/%d)",
        best,
        len(best),
        votes,
        len(candidates),
    )
    return best


async def _ocr_once(
    client: anthropic.AsyncAnthropic,
    *,
    model: str,
    media_type: str,
    b64: str,
    prompt: str,
    timeout: int,
    case_sensitive: bool,
) -> Optional[str]:
    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=model,
                max_tokens=8,
                temperature=0,
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
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            ),
            timeout=timeout,
        )
    except Exception as exc:
        logger.warning("Captcha OCR request failed: %s", exc)
        return None

    for block in response.content:
        if block.type == "text" and block.text.strip():
            result = normalize_captcha(block.text, case_sensitive=case_sensitive)
            if result:
                return result
    return None


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

    model = settings.sahiy_admin_captcha_model_resolved
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    timeout = max(settings.ai_timeout_seconds, 45)

    candidates: List[str] = []
    for prompt in (_PROMPT_PRIMARY, _PROMPT_RETRY, _PROMPT_PRIMARY):
        result = await _ocr_once(
            client,
            model=model,
            media_type=media_type,
            b64=b64,
            prompt=prompt,
            timeout=timeout,
            case_sensitive=case_sensitive,
        )
        if result:
            candidates.append(result)
            if len(result) == _CAPTCHA_LEN and candidates.count(result) >= 2:
                logger.info("Captcha OCR early match: %r", result)
                return result

    best = _pick_best_candidate(candidates)
    if best and len(best) != _CAPTCHA_LEN:
        logger.warning(
            "Captcha OCR length %d != expected %d — submitting anyway",
            len(best),
            _CAPTCHA_LEN,
        )
    elif not best:
        logger.warning("Captcha OCR returned no candidates")
    return best
