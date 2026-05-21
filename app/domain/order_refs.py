"""Extract order track numbers and Uzbek phone numbers from user text."""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

from app.domain.classification import ORDER_REF_PATTERN
from app.domain.entities import Message
from app.domain.enums import MessageRole
from app.domain.text_normalize import normalize_text

_DG_SN_RE = re.compile(r"\b(DG[-\s]?\d{4,14})\b", re.IGNORECASE)
# Express / client track: Botir-test-101, TRACKawdawd001
_EXPRESS_TRACK_RE = re.compile(
    r"\b([A-Za-z]{2,16}[-_][A-Za-z0-9][A-Za-z0-9_-]{2,40})\b",
)
# TRACK + letters/digits without separator
_PREFIXED_TRACK_RE = re.compile(r"\b(TRACK[A-Za-z0-9]{4,40})\b", re.IGNORECASE)
_LONG_NUMERIC_TRACK_RE = re.compile(r"\b(\d{12,20})\b")
# Generic token (letters+digits), allows hyphen inside
_TOKEN_TRACK_RE = re.compile(r"\b([A-Z0-9][A-Z0-9_-]{5,40})\b", re.IGNORECASE)
_LABELED_TRACK_RE = re.compile(
    r"\b(?:track(?:ing)?|trek|treking)\s*(?:raqam[i]?)?\s*[:#]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9_-]{3,42})"
    r"|\b(?:zakaz|buyurtma)\s+(?:raqam[i]?\s*)?[:#]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9_-]{3,42})",
    re.IGNORECASE,
)
_PHONE_CANDIDATE_RE = re.compile(r"\+?\d[\d\s\-]{8,18}\d")
_FOLLOWUP_HINT_RE = re.compile(r"\b(chi|chu|dachi|ham|unda)\b", re.IGNORECASE)

_ORDER_NOISE_WORDS = frozenset(
    {
        "meni",
        "mening",
        "menga",
        "bu",
        "shu",
        "zakaz",
        "zakazim",
        "zakazlarim",
        "zakazlar",
        "buyurtma",
        "buyurtmalarim",
        "buyurtmalar",
        "qayda",
        "buyurtmam",
        "qayerda",
        "qayer",
        "holat",
        "status",
        "track",
        "tracking",
        "raqam",
        "raqami",
    }
)


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def is_uzbek_mobile_digits(digits: str) -> bool:
    if len(digits) == 12 and digits.startswith("998"):
        return digits[3] == "9"
    if len(digits) == 9 and digits.startswith("9"):
        return True
    return False


def normalize_phone(phone: str) -> str:
    digits = _digits_only(phone)
    if digits.startswith("998") and len(digits) == 12:
        return digits
    if len(digits) == 9:
        return "998" + digits
    return digits


def _clean_track_token(token: str) -> str:
    return token.strip().strip(".,;:!?\"'").replace(" ", "")


def _score_track(token: str) -> int:
    t = token.upper()
    score = len(t)
    if t.startswith("DG"):
        score += 100
    if t.startswith("TRACK"):
        score += 80
    if "-" in t or "_" in t:
        score += 40
    if any(c.isalpha() for c in t) and any(c.isdigit() for c in t):
        score += 30
    if t.isdigit():
        score += 20
    return score


def _is_noise_token(token: str) -> bool:
    low = token.lower()
    if low in _ORDER_NOISE_WORDS:
        return True
    if len(low) < 4:
        return True
    return False


def extract_track(text: str) -> Optional[str]:
    """Best-effort track / order_sn / express_num from free-form user message."""
    if not text or not text.strip():
        return None

    candidates: List[str] = []

    labeled = _LABELED_TRACK_RE.search(text)
    if labeled:
        captured = next((g for g in labeled.groups() if g), None)
        if captured:
            token = _clean_track_token(captured)
            if not _is_noise_token(token):
                candidates.append(token)

    dg = _DG_SN_RE.search(text)
    if dg:
        candidates.append(re.sub(r"[\s-]", "", dg.group(1)).upper())

    for match in ORDER_REF_PATTERN.finditer(text):
        candidates.append(_clean_track_token(match.group(0)))

    for pattern in (_PREFIXED_TRACK_RE, _EXPRESS_TRACK_RE):
        for match in pattern.finditer(text):
            candidates.append(_clean_track_token(match.group(1)))

    for match in _LONG_NUMERIC_TRACK_RE.finditer(text):
        digits = match.group(1)
        if is_uzbek_mobile_digits(digits):
            continue
        candidates.append(digits)

    for match in _PHONE_CANDIDATE_RE.finditer(text):
        digits = _digits_only(match.group(0))
        if is_uzbek_mobile_digits(digits):
            continue

    upper = text.upper()
    for match in _TOKEN_TRACK_RE.finditer(upper):
        token = _clean_track_token(match.group(1))
        if _is_noise_token(token):
            continue
        digits = sum(ch.isdigit() for ch in token)
        letters = sum(ch.isalpha() for ch in token)
        if digits < 1:
            continue
        if letters < 1:
            if is_uzbek_mobile_digits(_digits_only(token)):
                continue
            if len(token) < 12:
                continue
        candidates.append(token)

    if not candidates:
        return None

    best = max(candidates, key=_score_track)
    if is_daigou_sn(best):
        return re.sub(r"[\s-]", "", best).upper()
    upper = best.upper()
    if upper.startswith("TRACK"):
        return upper
    return best


def is_daigou_sn(value: str) -> bool:
    cleaned = re.sub(r"[\s-]", "", value.strip().upper())
    return bool(re.fullmatch(r"DG\d{4,14}", cleaned))


def extract_phone(text: str) -> Optional[str]:
    """Only Uzbek mobile — long numeric tracks are not phones."""
    if extract_track(text):
        # Still allow explicit phone in same message if clearly labeled
        lowered = normalize_text(text)
        if not any(w in lowered for w in ("telefon", "tel", "nomer", "raqamim", "phone")):
            return None

    for match in _PHONE_CANDIDATE_RE.finditer(text):
        digits = _digits_only(match.group(0))
        if is_uzbek_mobile_digits(digits):
            return normalize_phone(match.group(0))
    return None


_DELIVERY_DELAY_WORDS = (
    "kelmayapti",
    "kelmay",
    "kelmag",
    "kelmagan",
    "kemayapti",
    "kemay",
    "kemagan",
    "kemadi",
    "yetkazilmagan",
    "yetkazilmadi",
    "olib kelinmagan",
    "olib kelmagan",
)

_ORDER_LOOKUP_STATUS_WORDS = (
    "qayerda",
    "qayer",
    "qayda",
    "holat",
    "status",
    "kuzat",
    "tracking",
    *_DELIVERY_DELAY_WORDS,
)

_ORDER_LOOKUP_CONTEXT_WORDS = (
    "zakaz",
    "zakazim",
    "zakazlarim",
    "buyurtma",
    "buyurtmam",
    "buyurtmalar",
    "buyurtmalarim",
    "tovar",
    "tovarim",
)


def is_order_lookup_request(text: str) -> bool:
    """Buyurtma API — track, ro'yxat, qayerda, kelmayapti."""
    if extract_track(text) or is_order_list_question(text):
        return True
    from app.domain.classification import has_order_reference

    if has_order_reference(text):
        return True
    lowered = normalize_text(text)
    if any(w in lowered for w in _DELIVERY_DELAY_WORDS):
        return True
    if any(w in lowered for w in _ORDER_LOOKUP_CONTEXT_WORDS) and any(
        w in lowered for w in _ORDER_LOOKUP_STATUS_WORDS
    ):
        return True
    return False


def is_order_list_question(text: str) -> bool:
    """Umumiy ro'yxat: «zakazlarim qayda», «barcha buyurtmalarim» — bitta track emas."""
    if extract_track(text):
        return False
    lowered = normalize_text(text)
    list_hints = (
        "zakazlarim",
        "zakazlar",
        "buyurtmalarim",
        "buyurtmalar",
        "hamma zakaz",
        "barcha buyurtma",
        "buyurtmalarim qayerda",
        "buyurtmalarim qayda",
    )
    if any(h in lowered for h in list_hints):
        return True
    if any(w in lowered for w in ("zakazlarim", "buyurtmalarim", "buyurtmalar", "buyurtmam")):
        if any(w in lowered for w in ("qayerda", "qayda", "holat", "royxat", "kor", "ko'r")):
            return True
    return False


def build_order_query_text(text: str, recent_messages: Sequence[Message]) -> str:
    """Merge thread for short follow-ups: '773402738804490 bu chi'."""
    if extract_track(text) or extract_phone(text):
        return text
    if not _FOLLOWUP_HINT_RE.search(text):
        return text

    parts: List[str] = [text]
    for msg in reversed(recent_messages):
        if msg.role != MessageRole.USER.value:
            continue
        if extract_track(msg.content) or extract_phone(msg.content):
            parts.insert(0, msg.content)
            break
    return " ".join(parts)
