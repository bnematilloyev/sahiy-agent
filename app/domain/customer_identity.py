"""Customer identification gate — phone format + Sahiy user_id verification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from app.domain.order_refs import (
    _digits_only,
    extract_phone,
    extract_track,
    is_uzbek_mobile_digits,
    normalize_phone,
)

_SAHIY_USER_ID_RE = re.compile(
    r"(?:user\s*id|userid|foydalanuvchi\s*id|sahiy\s*id|id)\s*[:#]?\s*(\d{3,10})\b",
    re.IGNORECASE,
)

IDENTITY_REQUIRED_TEXT = (
    "📱 Davom etish uchun Sahiy hisobingiz kerak.\n\n"
    "Quyidagilardan birini yuboring:\n"
    "🔹 Sahiy user ID — masalan: 111111 yoki id 111111\n"
    "🔹 Telefon — 998901234567 yoki «Telefon raqamni yuborish» tugmasi\n\n"
    "Tasdiqlangach savolingizga javob beraman."
)

SAHIY_USER_ID_VERIFIED_TEXT = (
    "✅ Sahiy user ID qabul qilindi. Endi savolingizni yozing."
)

INVALID_PHONE_FORMAT_TEXT = (
    "❌ Telefon formati noto'g'ri.\n\n"
    "To'g'ri misol: 998901234567 yoki +998 90 123 45 67\n"
    "Qayta yuboring."
)

PHONE_NOT_REGISTERED_TEXT = (
    "❌ Bu telefon Sahiy tizimida topilmadi.\n\n"
    "Ilovada ro'yxatdan o'tgan raqamni yuboring yoki "
    "«Telefon raqamni yuborish» tugmasidan foydalaning."
)

PHONE_VERIFIED_TEXT = (
    "✅ Telefon tasdiqlandi. Endi buyurtma yoki boshqa savolingizni yozing."
)

API_UNAVAILABLE_TEXT = (
    "Hozir mijozni tekshirib bo'lmadi (API vaqtincha ishlamayapti). "
    "Bir necha daqiqadan keyin qayta urinib ko'ring."
)


@dataclass(frozen=True)
class PhoneVerifyResult:
    ok: bool
    phone: Optional[str] = None
    sahiy_user_id: Optional[int] = None
    error: Optional[str] = None  # invalid_format | not_found | api_unavailable


def validate_uzbek_phone(phone: str) -> Optional[str]:
    """Return normalized 998XXXXXXXXX or None if format invalid."""
    if not phone or not str(phone).strip():
        return None
    normalized = normalize_phone(str(phone).strip())
    digits = _digits_only(normalized)
    if not is_uzbek_mobile_digits(digits):
        return None
    return normalized


def extract_sahiy_user_id(text: str) -> Optional[int]:
    """Sahiy DB user_id (mijoz id) — Telegram user_id emas."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    if extract_track(stripped):
        return None

    match = _SAHIY_USER_ID_RE.search(stripped)
    if match:
        return int(match.group(1))

    if re.fullmatch(r"\d{3,8}", stripped):
        return int(stripped)

    return None


def sahiy_phone_search_candidates(phone: str) -> List[str]:
    """API qidiruv uchun telefon variantlari (998… va qisqa formatlar)."""
    stripped = (phone or "").strip()
    if not stripped:
        return []

    out: List[str] = []
    standard = validate_uzbek_phone(stripped)
    if standard:
        out.append(standard)

    digits = _digits_only(stripped)
    if not digits or extract_track(digits):
        return list(dict.fromkeys(out))

    if 7 <= len(digits) <= 12:
        out.append(digits)
        if not digits.startswith("998"):
            out.append("998" + digits)

    from_text = extract_phone(stripped)
    if from_text:
        out.append(from_text)

    return list(dict.fromkeys(out))


def extract_registration_phone(text: str) -> Optional[str]:
    """Telefon matndan — standart 998… yoki Sahiy dagi qisqa format."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    if extract_sahiy_user_id(stripped) is not None and re.fullmatch(
        r"\d{3,8}", stripped
    ):
        return None

    candidates = sahiy_phone_search_candidates(stripped)
    return candidates[0] if candidates else None


def resolve_contact_phone(raw: str) -> Optional[str]:
    """Telegram contact.phone_number — o'z yoki boshqa kontakt kartasi."""
    return extract_registration_phone(raw or "")


def is_identity_only_message(text: str) -> bool:
    """Faqat ID yoki telefon yuborilgan — alohida tasdiq xabari."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    sid = extract_sahiy_user_id(stripped)
    if sid is not None:
        if str(sid) == stripped:
            return True
        if _SAHIY_USER_ID_RE.fullmatch(stripped) or _SAHIY_USER_ID_RE.search(stripped):
            return True
    phone = extract_registration_phone(stripped)
    if phone:
        compact = re.sub(r"\s+", "", stripped.lower())
        if compact in (
            phone,
            stripped,
            f"+{phone}",
            f"telefon{phone}",
            f"tel{phone}",
        ):
            return True
    return False


def requires_customer_identity(channel: str) -> bool:
    return channel == "telegram"
