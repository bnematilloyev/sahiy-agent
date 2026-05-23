"""Telegram uchun alohida guruh xabarlari — buyurtma zanjiri."""

from __future__ import annotations

from typing import Any, Dict, List

from app.domain.order_present import _display_sn, format_orders_message
from app.domain.reply_language import UZ_LAT, localize

_MAX_ITEMS = 6

_SECTION_META: Dict[str, Dict[str, Dict[str, str]]] = {
    "china_purchase": {
        "uz_lat": {"icon": "🇨🇳", "title": "Xitoyda (xarid)"},
        "uz_cyrl": {"icon": "🇨🇳", "title": "Хитойда (харид)"},
        "ru": {"icon": "🇨🇳", "title": "В Китае (закупка)"},
        "en": {"icon": "🇨🇳", "title": "In China (purchase)"},
        "zh": {"icon": "🇨🇳", "title": "在中国（采购）"},
    },
    "in_transit": {
        "uz_lat": {"icon": "🚚", "title": "Yo'lda"},
        "uz_cyrl": {"icon": "🚚", "title": "Yo'lda"},
        "ru": {"icon": "🚚", "title": "В пути"},
        "en": {"icon": "🚚", "title": "In transit"},
        "zh": {"icon": "🚚", "title": "运输中"},
    },
    "completed": {
        "uz_lat": {"icon": "✅", "title": "Qabul qilingan"},
        "uz_cyrl": {"icon": "✅", "title": "Qabul qilingan"},
        "ru": {"icon": "✅", "title": "Полученные"},
        "en": {"icon": "✅", "title": "Received"},
        "zh": {"icon": "✅", "title": "已签收"},
    },
}

_HINT: Dict[str, str] = {
    "uz_lat": "Batafsil bilish uchun track raqamni yuboring.",
    "uz_cyrl": "Батафсил: track рақамни юборинг.",
    "ru": "Подробнее: отправьте номер track.",
    "en": "For details, send your track number.",
    "zh": "详情：请发送tracking号码。",
}
_COMPLETED_HINT: Dict[str, str] = {
    "uz_lat": "Mahsulot va rasm uchun track raqamni yuboring.",
    "uz_cyrl": "Маҳсулот ва расм учун track рақамни юборинг.",
    "ru": "Для товара и фото отправьте номер track.",
    "en": "For product details and photos, send your track number.",
    "zh": "商品详情和图片：请发送tracking号码。",
}


def _pick(table: Dict[str, str], lang: str) -> str:
    return table.get(lang) or table.get(UZ_LAT, "")


def _section_header(section: Dict[str, Any], lang: str) -> str:
    key = str(section.get("key") or "")
    meta = _SECTION_META.get(key, {})
    block = meta.get(lang) or meta.get(UZ_LAT) or {"icon": "📦", "title": key}
    icon = block.get("icon", "📦")
    title = block.get("title", key)
    items = section.get("items") or []
    total = int(section.get("total") or len(items))
    shown = min(len(items), _MAX_ITEMS)
    if total > shown:
        count = f" ({shown}/{total})"
    elif total:
        count = f" ({total} ta)"
    else:
        count = ""
    return f"{icon} {title}{count}"


def _format_chain_item(item: Dict[str, Any], index: int) -> str:
    track = _display_sn(str(item.get("track") or "—"))
    line = f"{index}. {track}"
    date = (item.get("date") or "").strip()
    if date:
        line += f" — {date}"
    loc = (item.get("location") or "").strip()
    if loc:
        line += f" ({loc})"
    return line


def format_chain_section_message(section: Dict[str, Any], lang: str = UZ_LAT) -> str:
    items = section.get("items") or []
    if not items:
        return ""
    header = _section_header(section, lang)
    lines = [header, ""]
    for i, it in enumerate(items[:_MAX_ITEMS], 1):
        if isinstance(it, dict):
            lines.append(_format_chain_item(it, i))
    return "\n".join(lines)


def build_order_telegram_messages(
    data: Dict[str, Any],
    *,
    lang: str = UZ_LAT,
) -> List[str]:
    """Sarlavha + har bir bo'lim alohida xabar + qisqa yo'naltirish."""
    if data.get("error") or data.get("ownership_mismatch"):
        return [format_orders_message(data, reply_language=lang)]

    if data.get("order_focus") or data.get("daigou_focus") or data.get("requested_track"):
        return [format_orders_message(data, reply_language=lang)]

    chain = data.get("order_chain")
    if not chain or not isinstance(chain, list):
        return [format_orders_message(data, reply_language=lang)]

    scope = (data.get("list_scope") or "").strip()
    total = sum(int(s.get("total") or len(s.get("items") or [])) for s in chain if isinstance(s, dict))
    if scope:
        header = f"📋 {scope} ({total} ta)" if total else f"📋 {scope}"
    else:
        header = localize("orders_header", lang)
        if total:
            header = f"{header} ({total} ta)"

    messages: List[str] = [header]

    for section in chain:
        if not isinstance(section, dict):
            continue
        text = format_chain_section_message(section, lang)
        if text.strip():
            messages.append(text)

    if len(messages) == 1:
        return [localize("orders_empty", lang)]

    has_completed = any(
        isinstance(s, dict) and s.get("key") == "completed" for s in chain
    )
    messages.append(_pick(_COMPLETED_HINT if has_completed else _HINT, lang))
    return messages
