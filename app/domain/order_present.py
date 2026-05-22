"""Normalize API orders for customer-facing Telegram replies (order_sn, emojis)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from app.domain.order_match import find_order_in_data
from app.domain.reply_language import UZ_LAT, localize
from app.infrastructure.sahiy_api.status_maps import (
    daigou_label,
    dashboard_label,
    delivery_label,
    jiyun_label,
    map_chinese_status_name,
)

if TYPE_CHECKING:
    from app.infrastructure.sahiy_api.daigou_admin import DaigouOrderDetail, SkuInfo

_ORDER_SN_KEYS = (
    "order_sn",
    "express_num",
    "track_number",
    "client_order_sn",
    "logistics_sn",
    "shipment_sn",
    "sn",
)

# Bo'lim sarlavhalari (key → har bir tildagi matn)
_SECTION_TITLE: Dict[str, Dict[str, str]] = {
    "unpicked_delivery": {
        "uz_lat": "⏳ Olib ketilmagan",
        "uz_cyrl": "⏳ Олиб кетилмаган",
        "ru": "⏳ Не получено",
        "en": "⏳ Awaiting pickup",
        "zh": "⏳ 待取货",
    },
    "delivery_orders": {
        "uz_lat": "📦 Yetkazib berish",
        "uz_cyrl": "📦 Етказиб бериш",
        "ru": "📦 Доставка",
        "en": "📦 Delivery",
        "zh": "📦 配送",
    },
    "daigou_orders": {
        "uz_lat": "🇨🇳 Xitoy omborigacha",
        "uz_cyrl": "🇨🇳 Хитой омборигача",
        "ru": "🇨🇳 До склада в Китае",
        "en": "🇨🇳 To China warehouse",
        "zh": "🇨🇳 至中国仓库",
    },
    "jiyun_orders": {
        "uz_lat": "📦 Buyurtmalar",
        "uz_cyrl": "📦 Буюртмалар",
        "ru": "📦 Заказы",
        "en": "📦 Orders",
        "zh": "📦 订单",
    },
    "dashboard_orders": {
        "uz_lat": "📍 Filialda",
        "uz_cyrl": "📍 Филиалда",
        "ru": "📍 В филиале",
        "en": "📍 At branch",
        "zh": "📍 在分支机构",
    },
}

_SECTIONS = (
    ("unpicked_delivery", "unpicked"),
    ("delivery_orders", "delivery"),
    ("daigou_orders", "daigou"),
    ("jiyun_orders", "jiyun"),
    ("dashboard_orders", "dashboard"),
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_DEFAULT_MAX = 6


def _section_title(key: str, lang: str) -> str:
    titles = _SECTION_TITLE.get(key, {})
    return titles.get(lang) or titles.get(UZ_LAT, key)


def _unknown_status(lang: str) -> str:
    if lang == "ru":
        return "Неизвестный статус"
    if lang == "en":
        return "Unknown status"
    return "Noma'lum holat"


def _not_yours(lang: str) -> str:
    if lang == "ru":
        return "Этот заказ не принадлежит вам."
    if lang == "en":
        return "This order does not belong to you."
    return "Bu buyurtma sizga tegishli emas."


def _data_not_found(lang: str) -> str:
    if lang == "ru":
        return "Данные не найдены."
    if lang == "en":
        return "Data not found."
    return "Ma'lumot topilmadi."


def _order_label(lang: str) -> str:
    if lang == "ru":
        return "Заказ"
    if lang == "en":
        return "Order"
    return "Buyurtma"


def order_sn_from_row(row: Dict[str, Any]) -> str:
    for key in _ORDER_SN_KEYS:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "—"


def _format_date(value: Any) -> str:
    if not value:
        return ""
    raw = str(value).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            cleaned = raw[:26].replace("Z", "")
            dt = datetime.strptime(cleaned, fmt.replace("Z", ""))
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            continue
    if len(raw) >= 10 and raw[4] == "-":
        return f"{raw[8:10]}.{raw[5:7]}.{raw[0:4]}"
    return ""


def _status_code(row: Dict[str, Any]) -> Optional[int]:
    status = row.get("status")
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def status_text(row: Dict[str, Any], source: str, lang: str = UZ_LAT) -> str:
    code = _status_code(row)

    if source == "daigou":
        return daigou_label(code, lang)

    if source == "jiyun":
        if code is not None:
            return jiyun_label(code, lang)
        raw_name = row.get("status_name")
        if raw_name:
            mapped = map_chinese_status_name(str(raw_name), lang)
            if mapped:
                return mapped
            stripped = str(raw_name).strip()
            if not _CJK_RE.search(stripped):
                return stripped
        return _unknown_status(lang)

    if source == "dashboard":
        return dashboard_label(code, lang)

    if source in ("delivery", "unpicked"):
        if code is not None:
            return delivery_label(code, lang)
        label = row.get("status_label")
        if label and not _CJK_RE.search(str(label)):
            return str(label).strip()
        return _unknown_status(lang)

    return _unknown_status(lang)


def _location(row: Dict[str, Any], source: str) -> str:
    if source == "daigou":
        parts = [row.get("area_name"), row.get("sub_area_name")]
        return " — ".join(str(p).strip() for p in parts if p)
    branch = row.get("location_number") or row.get("branch_name") or ""
    return str(branch).strip() if branch else ""


def normalize_order_row(row: Dict[str, Any], source: str, lang: str = UZ_LAT) -> Dict[str, str]:
    return {
        "sn": order_sn_from_row(row),
        "holat": status_text(row, source, lang),
        "sana": _format_date(row.get("updated_at") or row.get("created_at") or row.get("paid_at")),
        "joy": _location(row, source),
    }


def _format_line(item: Dict[str, str]) -> str:
    line = f"🔹 {item.get('sn', '—')}\n   └ {item.get('holat', '—')}"
    if item.get("sana"):
        line += f", {item['sana']}"
    if item.get("joy"):
        line += f" — {item['joy']}"
    return line


def summarize_orders_for_prompt(
    data: Dict[str, Any],
    *,
    max_per_section: int = _DEFAULT_MAX,
    lang: str = UZ_LAT,
) -> Dict[str, Any]:
    if data.get("error"):
        return data

    sections: Dict[str, Any] = {}
    total = 0
    for key, source in _SECTIONS:
        rows = data.get(key) or []
        if not isinstance(rows, list) or not rows:
            continue
        extra = _coerce_int(data.get("daigou_total")) if key == "daigou_orders" else None
        count = extra if extra is not None and extra > len(rows) else len(rows)
        items = [
            normalize_order_row(row, source, lang)
            for row in rows[:max_per_section]
            if isinstance(row, dict)
        ]
        if items:
            title = _section_title(key, lang)
            sections[key] = {"sarlavha": title, "buyurtmalar": items, "jami": count}
            total += count

    out: Dict[str, Any] = {"jami": total, "bolimlar": sections}
    focus = data.get("daigou_focus")
    if isinstance(focus, dict):
        out["dg"] = normalize_order_row(focus, "daigou", lang)
    return out


def _format_focused_order(data: Dict[str, Any], lang: str = UZ_LAT) -> Optional[str]:
    order_focus = data.get("order_focus")
    if isinstance(order_focus, dict):
        row = order_focus.get("row")
        source = str(order_focus.get("source") or "delivery")
        if isinstance(row, dict):
            sn = order_sn_from_row(row)
            if not sn or sn == "—":
                return None
            item = normalize_order_row(row, source if source != "tracking" else "delivery", lang)
            label = _order_label(lang)
            return "\n".join(
                [
                    f"🔎 {label}: {sn}",
                    "_______",
                    "",
                    _format_line(item),
                    "",
                    "_______",
                ]
            ).strip()

    focus = data.get("daigou_focus")
    if isinstance(focus, dict):
        item = normalize_order_row(focus, "daigou", lang)
        sn = item.get("sn", "—")
        label = _order_label(lang)
        return "\n".join(
            [
                f"🔎 {label}: {sn}",
                "_______",
                "",
                _format_line(item),
                "",
                "_______",
            ]
        ).strip()
    return None


def _format_requested_track_fallback(
    data: Dict[str, Any], track: str, lang: str = UZ_LAT
) -> str:
    match = find_order_in_data(data, track)
    if match and isinstance(match.get("row"), dict):
        source = str(match.get("source") or "delivery")
        item = normalize_order_row(match["row"], source, lang)
        sn = item.get("sn") or track
        label = _order_label(lang)
        return "\n".join(
            [
                f"🔎 {label}: {sn}",
                "_______",
                "",
                _format_line(item),
                "",
                "_______",
            ]
        ).strip()
    return (
        f"🔎 {track}\n"
        "_______\n"
        + _not_yours(lang)
    )


def format_orders_message(
    data: Dict[str, Any],
    *,
    max_per_section: int = _DEFAULT_MAX,
    reply_language: str = UZ_LAT,
) -> str:
    lang = reply_language

    if data.get("error"):
        return data.get("message", _data_not_found(lang))
    if data.get("ownership_mismatch"):
        return data.get("message", _not_yours(lang))

    requested = data.get("requested_track")
    focused = _format_focused_order(data, lang)
    if focused:
        return focused

    if requested:
        return _format_requested_track_fallback(data, str(requested), lang)

    scope = data.get("list_scope")
    header = localize("orders_header", lang)
    lines: List[str] = [f"📋 {scope}" if scope else header]

    summary = summarize_orders_for_prompt(data, max_per_section=max_per_section, lang=lang)
    sections = summary.get("bolimlar") or {}
    if not sections:
        return localize("orders_empty", lang)

    shown_focus_sn = ""
    order_focus = data.get("order_focus")
    if isinstance(order_focus, dict) and isinstance(order_focus.get("row"), dict):
        shown_focus_sn = order_sn_from_row(order_focus["row"]).upper()
    elif isinstance(data.get("daigou_focus"), dict):
        shown_focus_sn = order_sn_from_row(data["daigou_focus"]).upper()

    for key, block in sections.items():
        title = block.get("sarlavha", _section_title(key, lang))
        orders = block.get("buyurtmalar") or []
        total = block.get("jami", len(orders))
        if not orders:
            continue
        lines.append("_______")
        if len(orders) < total:
            lines.append(f"{title} ({len(orders)}/{total})")
        else:
            lines.append(f"{title} ({total})")
        for item in orders:
            if key == "daigou_orders" and item.get("sn", "").upper() == shown_focus_sn:
                continue
            lines.append(_format_line(item))

    lines.append("_______")
    lines.append(localize("orders_track_hint", lang))
    return "\n".join(lines).strip()


def _coerce_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# ── SKU formatting ────────────────────────────────────────────────────────────

_SEP = "_______"

_SKU_HEADER: Dict[str, str] = {
    "uz_lat": "📦 Mahsulotlar",
    "uz_cyrl": "📦 Маҳсулотлар",
    "ru": "📦 Товары",
    "en": "📦 Products",
    "zh": "📦 商品",
}
_SKU_ITEM: Dict[str, str] = {
    "uz_lat": "Mahsulot",
    "uz_cyrl": "Маҳsulot",
    "ru": "Товар",
    "en": "Product",
    "zh": "商品",
}
_SKU_QTY: Dict[str, str] = {
    "uz_lat": "Miqdor",
    "uz_cyrl": "Миқдор",
    "ru": "Количество",
    "en": "Quantity",
    "zh": "数量",
}
_SKU_UNIT: Dict[str, str] = {
    "uz_lat": "Birlik narxi",
    "uz_cyrl": "Бирлик нархи",
    "ru": "Цена за шт",
    "en": "Unit price",
    "zh": "单价",
}
_SKU_LINE: Dict[str, str] = {
    "uz_lat": "Qator jami",
    "uz_cyrl": "Қator boʻyicha jami",
    "ru": "Сумма по позиции",
    "en": "Line total",
    "zh": "小计",
}
_SKU_TOTAL: Dict[str, str] = {
    "uz_lat": "Buyurtma jami",
    "uz_cyrl": "Буюртма жами",
    "ru": "Итого по заказу",
    "en": "Order total",
    "zh": "订单合计",
}
_SKU_STORE: Dict[str, str] = {
    "uz_lat": "Do'kon",
    "uz_cyrl": "Дўкон",
    "ru": "Магазин",
    "en": "Store",
    "zh": "店铺",
}
_QTY_UNIT: Dict[str, str] = {
    "uz_lat": "dona",
    "uz_cyrl": "дона",
    "ru": "шт",
    "en": "pcs",
    "zh": "件",
}
_UZS_SUFFIX: Dict[str, str] = {
    "uz_lat": "so'm",
    "uz_cyrl": "сўм",
    "ru": "сум",
    "en": "UZS",
    "zh": "UZS",
    "zh": "UZS",
}

_SPEC_KEYS: Dict[str, Dict[str, str]] = {
    "尺码": {"uz_lat": "O'lcham", "uz_cyrl": "Ўлчам", "ru": "Размер", "en": "Size", "zh": "尺码"},
    "尺寸": {"uz_lat": "O'lcham", "uz_cyrl": "Ўлчам", "ru": "Размер", "en": "Size", "zh": "尺寸"},
    "大小": {"uz_lat": "O'lcham", "uz_cyrl": "Ўлчам", "ru": "Размер", "en": "Size", "zh": "大小"},
    "颜色分类": {"uz_lat": "Rang", "uz_cyrl": "Ранг", "ru": "Цвет", "en": "Color", "zh": "颜色分类"},
    "颜色": {"uz_lat": "Rang", "uz_cyrl": "Ранг", "ru": "Цвет", "en": "Color", "zh": "颜色"},
    "规格": {"uz_lat": "Variant", "uz_cyrl": "Variant", "ru": "Вариант", "en": "Variant", "zh": "规格"},
    "spetsifikatsiyalar": {
        "uz_lat": "Spetsifikatsiya",
        "uz_cyrl": "Spetsifikatsiya",
        "ru": "Спецификация",
        "en": "Specification",
        "zh": "规格",
    },
    "型号": {"uz_lat": "Model", "uz_cyrl": "Модел", "ru": "Модель", "en": "Model", "zh": "型号"},
    "款式": {"uz_lat": "Model", "uz_cyrl": "Модел", "ru": "Модель", "en": "Style", "zh": "款式"},
    "容量": {"uz_lat": "Hajm", "uz_cyrl": "Ҳajm", "ru": "Объём", "en": "Capacity", "zh": "容量"},
    "套餐": {"uz_lat": "To'plam", "uz_cyrl": "Тўplam", "ru": "Комплект", "en": "Package", "zh": "套餐"},
    "材质": {"uz_lat": "Material", "uz_cyrl": "Material", "ru": "Материал", "en": "Material", "zh": "材质"},
    "长度": {"uz_lat": "Uzunlik", "uz_cyrl": "Uzunlik", "ru": "Длина", "en": "Length", "zh": "长度"},
    "宽度": {"uz_lat": "Kenglik", "uz_cyrl": "Kenglik", "ru": "Ширина", "en": "Width", "zh": "宽度"},
    "高度": {"uz_lat": "Balandlik", "uz_cyrl": "Balandlik", "ru": "Высота", "en": "Height", "zh": "高度"},
    "重量": {"uz_lat": "Og'irlik", "uz_cyrl": "Og'irlik", "ru": "Вес", "en": "Weight", "zh": "重量"},
}


def _t(labels: Dict[str, str], lang: str) -> str:
    return labels.get(lang) or labels.get(UZ_LAT) or next(iter(labels.values()))


def _truncate(text: str, limit: int = 100) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _localize_spec_label(raw_label: str, lang: str) -> str:
    key = raw_label.strip().rstrip(":：")
    if not key:
        return ""
    if key in _SPEC_KEYS:
        return _t(_SPEC_KEYS[key], lang)
    for zh, tr in _SPEC_KEYS.items():
        if zh in key:
            return _t(tr, lang)
    return key


def format_uzs(cny_amount: float, cny_to_uzs: float, lang: str = UZ_LAT) -> str:
    """Convert CNY amount to formatted UZS string."""
    suffix = _UZS_SUFFIX.get(lang) or _UZS_SUFFIX[UZ_LAT]
    uzs = int(round(cny_amount * cny_to_uzs))
    formatted = f"{uzs:,}".replace(",", " ")
    return f"{formatted} {suffix}"


def _format_money(cny: float, lang: str, cny_to_uzs: Optional[float]) -> str:
    if cny_to_uzs and cny_to_uzs > 0:
        return format_uzs(cny, cny_to_uzs, lang)
    return f"{cny:.2f} ¥"


def _format_sku_block(
    sku: "SkuInfo",
    index: int,
    lang: str,
    *,
    cny_to_uzs: Optional[float],
    multi: bool,
) -> List[str]:
    name = sku.name.strip() or f"SKU {index}"
    title = f"🔹 {_t(_SKU_ITEM, lang)} {index}" if multi else f"🔹 {_truncate(name, 80)}"
    lines: List[str] = [title]

    if multi or len(name) > 80:
        lines.append(f"   📝 {_truncate(name, 120)}")

    for spec in sku.specs:
        raw_l = str(spec.get("label", "")).strip()
        raw_v = str(spec.get("value", "")).strip()
        if not raw_l and not raw_v:
            continue
        label = _localize_spec_label(raw_l, lang) if raw_l else "—"
        value = raw_v or "—"
        lines.append(f"   └ {label}: {value}")

    qty_word = _t(_QTY_UNIT, lang)
    lines.append(f"   └ {_t(_SKU_QTY, lang)}: {sku.quantity} {qty_word}")
    lines.append(f"   └ {_t(_SKU_UNIT, lang)}: {_format_money(sku.actual_price, lang, cny_to_uzs)}")
    lines.append(f"   └ {_t(_SKU_LINE, lang)}: {_format_money(sku.amount, lang, cny_to_uzs)}")

    platform = (sku.platform or "").strip()
    if platform:
        lines.append(f"   └ {_t(_SKU_STORE, lang)}: {platform}")

    return lines


def format_sku_text(
    detail: "DaigouOrderDetail",
    lang: str = UZ_LAT,
    *,
    cny_to_uzs: Optional[float] = None,
) -> str:
    """Format DaigouOrderDetail SKU list as a Telegram-friendly text block."""
    if not detail.skus:
        return ""

    multi = len(detail.skus) > 1
    parts: List[str] = [_t(_SKU_HEADER, lang), _SEP, ""]

    for i, sku in enumerate(detail.skus, 1):
        parts.extend(_format_sku_block(sku, i, lang, cny_to_uzs=cny_to_uzs, multi=multi))
        if i < len(detail.skus):
            parts.append("")

    parts.extend(["", _SEP, f"💵 {_t(_SKU_TOTAL, lang)}: {_format_money(detail.amount, lang, cny_to_uzs)}"])
    return "\n".join(parts)


def collect_sku_images(detail: "DaigouOrderDetail", *, max_photos: int = 5) -> List[str]:
    """Collect up to max_photos unique image URLs from all SKUs."""
    seen: set[str] = set()
    urls: List[str] = []
    for sku in detail.skus:
        for img in sku.images:
            if img and img not in seen:
                seen.add(img)
                urls.append(img)
                if len(urls) >= max_photos:
                    return urls
    return urls
