"""Telegram uchun alohida guruh xabarlari — buyurtma zanjiri."""

from __future__ import annotations

from typing import Any, Dict, List

from app.domain.order_present import format_orders_message
from app.domain.reply_language import UZ_LAT, localize

_SEP = "━━━━━━━━━━━━━━━━"

_SECTION_META: Dict[str, Dict[str, Dict[str, str]]] = {
    "china_purchase": {
        "uz_lat": {"emoji": "🇨🇳", "title": "Xitoyda — xarid qilinmoqda"},
        "uz_cyrl": {"emoji": "🇨🇳", "title": "Хитойда — хarid qilinmoqda"},
        "ru": {"emoji": "🇨🇳", "title": "В Китае — оформление заказа"},
        "en": {"emoji": "🇨🇳", "title": "In China — being purchased"},
        "zh": {"emoji": "🇨🇳", "title": "在中国 — 采购中"},
    },
    "in_transit": {
        "uz_lat": {"emoji": "🚚", "title": "Yo'lda / yetkazilmoqda"},
        "uz_cyrl": {"emoji": "🚚", "title": "Йўлда / yetkazilmoqda"},
        "ru": {"emoji": "🚚", "title": "В пути / доставляется"},
        "en": {"emoji": "🚚", "title": "On the way / in delivery"},
        "zh": {"emoji": "🚚", "title": "运输中 / 配送中"},
    },
}

_HEADER: Dict[str, str] = {
    "uz_lat": "Kutilayotgan buyurtmalar",
    "uz_cyrl": "Kutilayotgan buyurtmalar",
    "ru": "Заказы в процессе",
    "en": "Orders in progress",
    "zh": "进行中的订单",
}

_HINT: Dict[str, str] = {
    "uz_lat": "💡 Batafsil: track raqam (DG… yoki TRACK…) yuboring.",
    "uz_cyrl": "💡 Batafsil: track raqam (DG… yoki TRACK…) yuboring.",
    "ru": "💡 Подробнее: отправьте номер track (DG… или TRACK…).",
    "en": "💡 Details: send a track number (DG… or TRACK…).",
    "zh": "💡 详情：请发送tracking号码（DG…或TRACK…）。",
}


def _pick(table: Dict[str, str], lang: str) -> str:
    return table.get(lang) or table.get(UZ_LAT, "")


def _section_header(section: Dict[str, Any], lang: str) -> str:
    key = str(section.get("key") or "")
    meta = _SECTION_META.get(key, {})
    block = meta.get(lang) or meta.get(UZ_LAT) or {"emoji": "📦", "title": key}
    emoji = block.get("emoji", "📦")
    title = block.get("title", key)
    items = section.get("items") or []
    total = int(section.get("total") or len(items))
    shown = len(items)
    if shown < total:
        count = f" ({shown}/{total})"
    else:
        count = f" ({total})" if total else ""
    return f"{emoji} {title}{count}"


def _format_chain_item(item: Dict[str, Any], *, phase: str) -> str:
    track = item.get("track") or "—"
    status = item.get("status") or "—"
    icon = "📋" if phase == "china_purchase" else "🚚"
    lines = [f"{icon} {track}", f"   ✨ {status}"]
    if item.get("location"):
        lines.append(f"   📍 {item['location']}")
    for extra in item.get("extras") or []:
        lines.append(f"   {extra}")
    if item.get("date"):
        lines.append(f"   🗓 {item['date']}")
    return "\n".join(lines)


def format_chain_section_message(section: Dict[str, Any], lang: str = UZ_LAT) -> str:
    """Bitta bo'lim — alohida Telegram xabari."""
    items = section.get("items") or []
    if not items:
        return ""
    phase = str(section.get("key") or "")
    header = _section_header(section, lang)
    blocks = [_format_chain_item(it, phase=phase) for it in items if isinstance(it, dict)]
    body = f"\n\n{_SEP}\n\n".join(blocks)
    return f"{header}\n\n{_SEP}\n\n{body}"


def build_order_telegram_messages(
    data: Dict[str, Any],
    *,
    lang: str = UZ_LAT,
) -> List[str]:
    """
    Telegram ga ketadigan xabarlar ro'yxati.
    Birinchi — sarlavha; keyingilari — har bir status guruhi; oxirgi — hint.
    """
    if data.get("error") or data.get("ownership_mismatch"):
        return [format_orders_message(data, reply_language=lang)]

    if data.get("order_focus") or data.get("daigou_focus") or data.get("requested_track"):
        return [format_orders_message(data, reply_language=lang)]

    chain = data.get("order_chain")
    if not chain or not isinstance(chain, list):
        return [format_orders_message(data, reply_language=lang)]

    scope = data.get("list_scope")
    title = scope if scope else _pick(_HEADER, lang)
    messages: List[str] = [f"📋 {title}" if not str(title).startswith("📋") else str(title)]

    for section in chain:
        if not isinstance(section, dict):
            continue
        text = format_chain_section_message(section, lang)
        if text:
            messages.append(text)

    if len(messages) == 1:
        return [localize("orders_empty", lang)]

    messages.append(_pick(_HINT, lang))
    return messages
