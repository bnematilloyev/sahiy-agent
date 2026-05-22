"""Taxminiy yetkazish vaqti — Sahiy logistika statuslari (1–12) bo'yicha."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from app.domain.reply_language import UZ_CYRL, UZ_LAT
from app.domain.text_normalize import normalize_text

# Default kun (keyingi bosqichlar yig'indisi uchun)
LOGISTICS_DEFAULT_DAYS: Dict[int, Optional[int]] = {
    1: 1,
    2: 3,
    3: 1,
    4: 4,
    5: 5,
    6: 1,
    7: 1,
    8: 1,
    9: 2,
    10: 1,
    11: 3,
    12: None,
}

LOGISTICS_STATUS_LABELS: Dict[int, Dict[str, str]] = {
    1: {
        UZ_LAT: "Sotib olindi",
        UZ_CYRL: "Сотиб olindi",
        "ru": "Куплено",
        "en": "Purchased",
        "zh": "已购买",
    },
    2: {
        UZ_LAT: "Omborga yo'lda",
        UZ_CYRL: "Omborga yo'lda",
        "ru": "В пути на склад",
        "en": "On the way to warehouse",
        "zh": "运往仓库途中",
    },
    3: {
        UZ_LAT: "Sahiy (Xitoy) omborida",
        UZ_CYRL: "Sahiy (Xitoy) omborida",
        "ru": "На складе Sahiy (Китай)",
        "en": "At Sahiy warehouse (China)",
        "zh": "Sahiy中国仓库",
    },
    4: {
        UZ_LAT: "Qirg'izistonga yo'lda",
        UZ_CYRL: "Qirg'izistonga yo'lda",
        "ru": "В пути в Кыргызстан",
        "en": "On the way to Kyrgyzstan",
        "zh": "运往吉尔吉斯斯坦途中",
    },
    5: {
        UZ_LAT: "O'zbekistonga yo'lda",
        UZ_CYRL: "O'zbekistonga yo'lda",
        "ru": "В пути в Узбекистан",
        "en": "On the way to Uzbekistan",
        "zh": "运往乌兹别克斯坦途中",
    },
    6: {
        UZ_LAT: "Toshkentda",
        UZ_CYRL: "Toshkentda",
        "ru": "В Ташкенте",
        "en": "In Tashkent",
        "zh": "在塔什干",
    },
    7: {
        UZ_LAT: "Markaziy punktda",
        UZ_CYRL: "Markaziy punktda",
        "ru": "На центральном пункте",
        "en": "At central pickup point",
        "zh": "在中央取货点",
    },
    8: {
        UZ_LAT: "Mijozga kuryerda",
        UZ_CYRL: "Mijozga kuryerda",
        "ru": "Курьер везёт клиенту",
        "en": "Courier to customer",
        "zh": "快递员配送中",
    },
    9: {
        UZ_LAT: "Markaziy punktga kuryerda",
        UZ_CYRL: "Markaziy punktga kuryerda",
        "ru": "Курьер везёт на пункт",
        "en": "Courier to pickup point",
        "zh": "送往取货点途中",
    },
    10: {
        UZ_LAT: "Postomatga kuryerda",
        UZ_CYRL: "Postomatga kuryerda",
        "ru": "Курьер везёт в постомат",
        "en": "Courier to locker",
        "zh": "送往自取柜途中",
    },
    11: {
        UZ_LAT: "Postomatda",
        UZ_CYRL: "Postomatda",
        "ru": "В постомате",
        "en": "In pickup locker",
        "zh": "在自取柜",
    },
    12: {
        UZ_LAT: "Yetkazildi",
        UZ_CYRL: "Yetkazildi",
        "ru": "Доставлено",
        "en": "Delivered",
        "zh": "已送达",
    },
}

_DAIGOU_TO_LOGISTICS: Dict[int, int] = {
    0: 1,
    1: 1,
    2: 2,
    3: 1,
    4: 2,
    5: 3,
    6: 4,
}

_JIYUN_TO_LOGISTICS: Dict[int, int] = {
    1: 3,
    2: 3,
    3: 3,
    4: 4,
    5: 12,
}

_DELIVERY_TO_LOGISTICS: Dict[int, int] = {
    1: 3,
    2: 4,
    3: 5,
    4: 7,
    5: 11,
    6: 9,
    7: 12,
    8: 8,
}

_ETA_HINTS = (
    "qachon kel",
    "necha kun",
    "qancha kun",
    "qancha vaqt",
    "qancha kunda",
    "yetib keladi",
    "yetkaziladi",
    "taxminan qachon",
    "kogda pridet",
    "kogda budet",
    "skolko dney",
    "cherez skolko",
    "when will",
    "when arrive",
    "how many days",
    "how long",
    "什么时候",
    "几天",
    "多久",
    "何时到",
)

_ETA_DELIVERED: Dict[str, str] = {
    UZ_LAT: "✅ Buyurtma allaqachon yetkazilgan.",
    UZ_CYRL: "✅ Buyurtma allaqachon yetkazilgan.",
    "ru": "✅ Заказ уже доставлен.",
    "en": "✅ The order has already been delivered.",
    "zh": "✅ 订单已送达。",
}

_ETA_ESTIMATE: Dict[str, str] = {
    UZ_LAT: "⏱ Hozirgi bosqich: {status}\n📅 Taxminiy yetkazish: ~{days} kun ichida",
    UZ_CYRL: "⏱ Hozirgi bosqich: {status}\n📅 Taxminiy yetkazish: ~{days} kun ichida",
    "ru": "⏱ Текущий этап: {status}\n📅 Примерная доставка: ~{days} дн.",
    "en": "⏱ Current stage: {status}\n📅 Estimated delivery: within ~{days} days",
    "zh": "⏱ 当前阶段：{status}\n📅 预计送达：约 {days} 天内",
}

_ETA_UNKNOWN: Dict[str, str] = {
    UZ_LAT: "⏱ Aniq muddat uchun buyurtma track raqamini yuboring.",
    UZ_CYRL: "⏱ Aniq muddat uchun buyurtma track raqamini yuboring.",
    "ru": "⏱ Для точного срока отправьте номер track заказа.",
    "en": "⏱ Send the order track number for a precise estimate.",
    "zh": "⏱ 请发送订单tracking号码以获得准确预估。",
}


def is_eta_question(text: str) -> bool:
    lowered = normalize_text(text or "")
    if not lowered:
        return False
    return any(h in lowered for h in _ETA_HINTS)


def logistics_status_label(status: int, lang: str = UZ_LAT) -> str:
    labels = LOGISTICS_STATUS_LABELS.get(status, {})
    return labels.get(lang) or labels.get(UZ_LAT) or str(status)


def estimate_remaining_days(logistics_status: int) -> Optional[int]:
    """Joriy bosqichdan 11-gacha default kunlarni yig'adi. 12 = yetkazilgan."""
    if logistics_status >= 12:
        return 0
    if logistics_status < 1:
        logistics_status = 1
    total = 0
    for step in range(logistics_status, 12):
        days = LOGISTICS_DEFAULT_DAYS.get(step)
        if days:
            total += days
    return total


def _parse_logistics_info(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def resolve_logistics_status(row: Dict[str, Any], source: str) -> Optional[int]:
    """logistics_info.current_status yoki manba bo'yicha fallback xarita."""
    info = _parse_logistics_info(row.get("logistics_info"))
    if info:
        try:
            code = int(info.get("current_status"))
            if 1 <= code <= 12:
                return code
        except (TypeError, ValueError):
            pass

    try:
        raw_status = int(row.get("status")) if row.get("status") is not None else None
    except (TypeError, ValueError):
        return None
    if raw_status is None:
        return None

    src = source if source != "tracking" else "delivery"
    if src == "daigou":
        return _DAIGOU_TO_LOGISTICS.get(raw_status)
    if src == "jiyun":
        return _JIYUN_TO_LOGISTICS.get(raw_status)
    if src in ("delivery", "unpicked"):
        return _DELIVERY_TO_LOGISTICS.get(raw_status)
    return None


def pick_order_for_eta(data: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], str]]:
    order_focus = data.get("order_focus")
    if isinstance(order_focus, dict) and isinstance(order_focus.get("row"), dict):
        src = str(order_focus.get("source") or "delivery")
        if src == "tracking":
            src = "delivery"
        return order_focus["row"], src

    focus = data.get("daigou_focus")
    if isinstance(focus, dict):
        return focus, "daigou"

    for field, source in (
        ("unpicked_delivery", "delivery"),
        ("jiyun_orders", "jiyun"),
        ("delivery_orders", "delivery"),
        ("daigou_orders", "daigou"),
    ):
        rows = data.get(field) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            status = resolve_logistics_status(row, source)
            if status is not None and status < 12:
                return row, source
    return None


def format_eta_from_status(status: int, lang: str = UZ_LAT) -> str:
    lang = lang if lang in _ETA_ESTIMATE else UZ_LAT
    if status >= 12:
        return _ETA_DELIVERED.get(lang) or _ETA_DELIVERED[UZ_LAT]
    days = estimate_remaining_days(status)
    if days is None or days <= 0:
        return _ETA_DELIVERED.get(lang) or _ETA_DELIVERED[UZ_LAT]
    label = logistics_status_label(status, lang)
    template = _ETA_ESTIMATE.get(lang) or _ETA_ESTIMATE[UZ_LAT]
    return template.format(status=label, days=days)


def format_eta_message(
    row: Dict[str, Any],
    source: str,
    lang: str = UZ_LAT,
) -> Optional[str]:
    status = resolve_logistics_status(row, source)
    if status is None:
        return None
    return format_eta_from_status(status, lang)


def append_eta_to_reply(text: str, data: Dict[str, Any], query: str, lang: str = UZ_LAT) -> str:
    """Savol ETA bo'lsa va buyurtma topilsa — javobga taxmin qo'shadi."""
    if not is_eta_question(query):
        return text
    if data.get("error") or data.get("ownership_mismatch"):
        return text
    picked = pick_order_for_eta(data)
    if not picked:
        unknown = _ETA_UNKNOWN.get(lang) or _ETA_UNKNOWN[UZ_LAT]
        if unknown not in text:
            return f"{text.rstrip()}\n\n{unknown}"
        return text
    row, source = picked
    eta = format_eta_message(row, source, lang)
    if not eta or eta in text:
        return text
    return f"{text.rstrip()}\n\n{eta}"
