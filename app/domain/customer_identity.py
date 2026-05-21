"""Customer identification gate — phone format + Sahiy user_id verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.domain.order_refs import (
    _digits_only,
    extract_phone,
    is_uzbek_mobile_digits,
    normalize_phone,
)

IDENTITY_REQUIRED_TEXT = (
    "📱 Davom etish uchun telefon raqamingiz kerak.\n\n"
    "«Telefon raqamni yuborish» tugmasini bosing yoki "
    "998901234567 formatda yozing.\n\n"
    "Telefon tasdiqlanguncha boshqa savollarga javob berilmaydi."
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


def extract_registration_phone(text: str) -> Optional[str]:
    """Phone from contact-style message (998... only or labeled)."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    digits = _digits_only(stripped)
    if is_uzbek_mobile_digits(digits) and len(stripped) <= 20:
        return validate_uzbek_phone(stripped)
    return extract_phone(stripped)


def requires_customer_identity(channel: str) -> bool:
    return channel == "telegram"
