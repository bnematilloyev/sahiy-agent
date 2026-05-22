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

_IDENTITY_REQUIRED: dict[str, str] = {
    "uz_lat": (
        "📱 Davom etish uchun Sahiy hisobingiz kerak.\n\n"
        "Quyidagilardan birini yuboring:\n"
        "🔹 Sahiy user ID — masalan: 111111 yoki id 111111\n"
        "🔹 Telefon — 998901234567 yoki «Telefon raqamni yuborish» tugmasi\n\n"
        "Tasdiqlangach savolingizga javob beraman."
    ),
    "uz_cyrl": (
        "📱 Давом этиш учун Sahiy ҳисобингиз керак.\n\n"
        "Қуйидагилардан бирини юборинг:\n"
        "🔹 Sahiy user ID — масалан: 111111 ёки id 111111\n"
        "🔹 Телефон — 998901234567 ёки «Телефон рақамни юбориш» тугмаси\n\n"
        "Тасдиқлангач саволингизга жавоб бераман."
    ),
    "ru": (
        "📱 Для продолжения необходим аккаунт Sahiy.\n\n"
        "Отправьте одно из следующего:\n"
        "🔹 Sahiy user ID — например: 111111 или id 111111\n"
        "🔹 Телефон — 998901234567 или кнопка «Отправить номер телефона»\n\n"
        "После подтверждения отвечу на ваш вопрос."
    ),
    "en": (
        "📱 A Sahiy account is required to continue.\n\n"
        "Please send one of the following:\n"
        "🔹 Sahiy user ID — e.g.: 111111 or id 111111\n"
        "🔹 Phone — 998901234567 or tap «Send phone number»\n\n"
        "I'll answer your question after verification."
    ),
    "zh": (
        "📱 继续操作需要Sahiy账户。\n\n"
        "请发送以下其中一项：\n"
        "🔹 Sahiy用户ID — 例如：111111 或 id 111111\n"
        "🔹 电话 — 998901234567 或点击«发送电话号码»\n\n"
        "验证后我将回答您的问题。"
    ),
}

_INVALID_PHONE_FORMAT: dict[str, str] = {
    "uz_lat": "❌ Telefon formati noto'g'ri.\n\nTo'g'ri misol: 998901234567 yoki +998 90 123 45 67\nQayta yuboring.",
    "uz_cyrl": "❌ Телефон формати нотўғри.\n\nТўғри мисол: 998901234567 ёки +998 90 123 45 67\nҚайта юборинг.",
    "ru": "❌ Неверный формат номера телефона.\n\nПример: 998901234567 или +998 90 123 45 67\nОтправьте снова.",
    "en": "❌ Invalid phone format.\n\nExample: 998901234567 or +998 90 123 45 67\nPlease send again.",
    "zh": "❌ 电话格式不正确。\n\n示例：998901234567 或 +998 90 123 45 67\n请重新发送。",
}

_PHONE_NOT_REGISTERED: dict[str, str] = {
    "uz_lat": "❌ Bu telefon Sahiy tizimida topilmadi.\n\nIlovada ro'yxatdan o'tgan raqamni yuboring yoki «Telefon raqamni yuborish» tugmasidan foydalaning.",
    "uz_cyrl": "❌ Бу телефон Sahiy тизимида топилмади.\n\nИловада рўйхатдан ўтган рақамни юборинг ёки «Телефон рақамни юбориш» тугмасидан фойдаланинг.",
    "ru": "❌ Этот телефон не найден в системе Sahiy.\n\nОтправьте номер, зарегистрированный в приложении, или используйте кнопку «Отправить номер телефона».",
    "en": "❌ This phone number was not found in Sahiy system.\n\nSend the number registered in the app, or use the «Send phone number» button.",
    "zh": "❌ 该电话号码在Sahiy系统中未找到。\n\n请发送在应用程序中注册的号码，或使用«发送电话号码»按钮。",
}

_PHONE_VERIFIED: dict[str, str] = {
    "uz_lat": "✅ Telefon tasdiqlandi. Endi buyurtma yoki boshqa savolingizni yozing.",
    "uz_cyrl": "✅ Телефон тасдиқланди. Энди буюртма ёки бошқа саволингизни ёзинг.",
    "ru": "✅ Телефон подтверждён. Теперь напишите ваш вопрос.",
    "en": "✅ Phone confirmed. Now write your question.",
    "zh": "✅ 电话已确认。请提出您的问题。",
}

_API_UNAVAILABLE: dict[str, str] = {
    "uz_lat": "Hozir mijozni tekshirib bo'lmadi (API vaqtincha ishlamayapti). Bir necha daqiqadan keyin qayta urinib ko'ring.",
    "uz_cyrl": "Ҳозир мижозни текшириб бўлмади (API вақтинча ишламаяпти). Бир неча дақиқадан кейин қайта уриниб кўринг.",
    "ru": "Не удалось проверить аккаунт (API временно недоступен). Попробуйте снова через несколько минут.",
    "en": "Could not verify account (API temporarily unavailable). Please try again in a few minutes.",
    "zh": "无法验证账户（API暂时不可用）。请几分钟后重试。",
}


def _t(table: dict[str, str], lang: str) -> str:
    return table.get(lang) or table.get("uz_lat", "")


def identity_required_text(lang: str = "uz_lat") -> str:
    return _t(_IDENTITY_REQUIRED, lang)


def invalid_phone_format_text(lang: str = "uz_lat") -> str:
    return _t(_INVALID_PHONE_FORMAT, lang)


def phone_not_registered_text(lang: str = "uz_lat") -> str:
    return _t(_PHONE_NOT_REGISTERED, lang)


def phone_verified_text(lang: str = "uz_lat") -> str:
    return _t(_PHONE_VERIFIED, lang)


def api_unavailable_text(lang: str = "uz_lat") -> str:
    return _t(_API_UNAVAILABLE, lang)


# Backward-compatible constants (UZ default — avvalgi ishlatganlar uchun)
IDENTITY_REQUIRED_TEXT = _t(_IDENTITY_REQUIRED, "uz_lat")
SAHIY_USER_ID_VERIFIED_TEXT = "✅ Sahiy user ID qabul qilindi. Endi savolingizni yozing."
INVALID_PHONE_FORMAT_TEXT = _t(_INVALID_PHONE_FORMAT, "uz_lat")
PHONE_NOT_REGISTERED_TEXT = _t(_PHONE_NOT_REGISTERED, "uz_lat")
PHONE_VERIFIED_TEXT = _t(_PHONE_VERIFIED, "uz_lat")
API_UNAVAILABLE_TEXT = _t(_API_UNAVAILABLE, "uz_lat")


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
