"""Telegram uchun alohida guruh xabarlari — buyurtma zanjiri."""

from __future__ import annotations

from typing import Any, Dict, List

from app.domain.order_present import format_orders_message
from app.domain.reply_language import UZ_LAT, localize

_MAX_ITEMS = 6
_SEP = "──────────────────────"

_SECTION_META: Dict[str, Dict[str, Dict[str, str]]] = {
    "china_purchase": {
        "uz_lat": {"icon": "🇨🇳", "title": "Xitoyda (xarid)"},
        "uz_cyrl": {"icon": "🇨🇳", "title": "Xitoyda (xarid)"},
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
}

_HINT: Dict[str, str] = {
    "uz_lat": "💡 Batafsil: track raqam (DG… yoki raqam) yuboring.",
    "uz_cyrl": "💡 Batafsil: track raqam (DG… yoki raqam) yuboring.",
    "ru": "💡 Подробнее: отправьте track (DG… или номер).",
    "en": "💡 Details: send a track number (DG… or numeric track).",
    "zh": "💡 详情：请发送tracking号码。",
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
        count = f" · {shown}/{total}"
    elif total:
        count = f" · {total}"
    else:
        count = ""
    return f"{icon} {title}{count}"


def _format_extra_line(extra: str) -> str:
    text = extra.strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith(("to'lov", "toʻlov", "tolov", "oplata", "payment", "付款")):
        return f"   └ 💳 {text}"
    return f"   └ {text}"


def _format_chain_item(item: Dict[str, Any]) -> str:
    track = item.get("track") or "—"
    status = item.get("status") or "—"
    lines = [f"🔹 {track}", f"   └ {status}"]
    loc = (item.get("location") or "").strip()
    if loc:
        lines.append(f"   └ 📍 {loc}")
    for extra in item.get("extras") or []:
        line = _format_extra_line(str(extra))
        if line:
            lines.append(line)
    date = (item.get("date") or "").strip()
    if date:
        lines.append(f"   └ 📅 {date}")
    return "\n".join(lines)


def format_chain_section_message(section: Dict[str, Any], lang: str = UZ_LAT) -> str:
    items = section.get("items") or []
    if not items:
        return ""
    header = _section_header(section, lang)
    blocks = [
        _format_chain_item(it)
        for it in items[:_MAX_ITEMS]
        if isinstance(it, dict)
    ]
    return header + "\n" + _SEP + "\n\n" + "\n\n".join(blocks)


def build_order_telegram_messages(
    data: Dict[str, Any],
    *,
    lang: str = UZ_LAT,
) -> List[str]:
    """Sarlavha + har bir bo'lim alohida xabar + qisqa hint."""
    if data.get("error") or data.get("ownership_mismatch"):
        return [format_orders_message(data, reply_language=lang)]

    if data.get("order_focus") or data.get("daigou_focus") or data.get("requested_track"):
        return [format_orders_message(data, reply_language=lang)]

    chain = data.get("order_chain")
    if not chain or not isinstance(chain, list):
        return [format_orders_message(data, reply_language=lang)]

    scope = (data.get("list_scope") or "").strip()
    if scope:
        header = scope if scope.startswith("📋") else f"📋 {scope}"
    else:
        header = localize("orders_header", lang)

    messages: List[str] = [header]

    for section in chain:
        if not isinstance(section, dict):
            continue
        text = format_chain_section_message(section, lang)
        if text.strip():
            messages.append(text)

    if len(messages) == 1:
        return [localize("orders_empty", lang)]

    messages.append(_pick(_HINT, lang))
    return messages
