"""Normalize API orders for customer-facing Telegram replies (order_sn, emojis)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.domain.order_match import find_order_in_data
from app.infrastructure.sahiy_api.status_maps import (
    daigou_label,
    dashboard_label,
    delivery_label,
    jiyun_label,
)

_ORDER_SN_KEYS = (
    "order_sn",
    "express_num",
    "track_number",
    "client_order_sn",
    "logistics_sn",
    "shipment_sn",
    "sn",
)

_STATUS_NAME_UZ: Dict[str, str] = {
    "已发货": "Jo'natilgan",
    "待付款": "To'lov kutilmoqda",
    "待发货": "Jo'natish kutilmoqda",
    "已签收": "Qabul qilingan",
    "运输中": "Yo'lda",
}

_SECTIONS = (
    ("unpicked_delivery", "⏳ Olib ketilmagan", "unpicked"),
    ("delivery_orders", "📦 Yetkazib berish", "delivery"),
    ("daigou_orders", "🇨🇳 Xitoy omborigacha", "daigou"),
    ("jiyun_orders", "📦 Buyurtmalar", "jiyun"),
    ("dashboard_orders", "📍 Filialda", "dashboard"),
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_DEFAULT_MAX = 6


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


def _map_status_name(name: str) -> Optional[str]:
    stripped = name.strip()
    if stripped in _STATUS_NAME_UZ:
        return _STATUS_NAME_UZ[stripped]
    if _CJK_RE.search(stripped):
        return None
    return stripped


def status_text(row: Dict[str, Any], source: str) -> str:
    code = _status_code(row)

    if source == "daigou":
        return daigou_label(code)

    if source == "jiyun":
        if code is not None:
            return jiyun_label(code)
        raw_name = row.get("status_name")
        if raw_name:
            mapped = _map_status_name(str(raw_name))
            if mapped:
                return mapped
        return "Noma'lum holat"

    if source == "dashboard":
        return dashboard_label(code)

    if source in ("delivery", "unpicked"):
        if code is not None:
            return delivery_label(code)
        label = row.get("status_label")
        if label and not _CJK_RE.search(str(label)):
            return str(label).strip()
        return "Noma'lum holat"

    return "Noma'lum holat"


def _location(row: Dict[str, Any], source: str) -> str:
    if source == "daigou":
        parts = [row.get("area_name"), row.get("sub_area_name")]
        return " — ".join(str(p).strip() for p in parts if p)
    branch = row.get("location_number") or row.get("branch_name") or ""
    return str(branch).strip() if branch else ""


def normalize_order_row(row: Dict[str, Any], source: str) -> Dict[str, str]:
    return {
        "sn": order_sn_from_row(row),
        "holat": status_text(row, source),
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


def summarize_orders_for_prompt(data: Dict[str, Any], *, max_per_section: int = _DEFAULT_MAX) -> Dict[str, Any]:
    if data.get("error"):
        return data

    sections: Dict[str, Any] = {}
    total = 0
    for key, title, source in _SECTIONS:
        rows = data.get(key) or []
        if not isinstance(rows, list) or not rows:
            continue
        extra = _coerce_int(data.get("daigou_total")) if key == "daigou_orders" else None
        count = extra if extra is not None and extra > len(rows) else len(rows)
        items = [
            normalize_order_row(row, source)
            for row in rows[:max_per_section]
            if isinstance(row, dict)
        ]
        if items:
            sections[key] = {"sarlavha": title, "buyurtmalar": items, "jami": count}
            total += count

    out: Dict[str, Any] = {"jami": total, "bolimlar": sections}
    focus = data.get("daigou_focus")
    if isinstance(focus, dict):
        out["dg"] = normalize_order_row(focus, "daigou")
    return out


def _format_focused_order(data: Dict[str, Any]) -> Optional[str]:
    order_focus = data.get("order_focus")
    if isinstance(order_focus, dict):
        row = order_focus.get("row")
        source = str(order_focus.get("source") or "delivery")
        if isinstance(row, dict):
            sn = order_sn_from_row(row)
            if not sn or sn == "—":
                return None
            item = normalize_order_row(row, source if source != "tracking" else "delivery")
            return "\n".join(
                [
                    f"🔎 Buyurtma: {sn}",
                    "_______",
                    "",
                    _format_line(item),
                    "",
                    "_______",
                ]
            ).strip()

    focus = data.get("daigou_focus")
    if isinstance(focus, dict):
        item = normalize_order_row(focus, "daigou")
        sn = item.get("sn", "—")
        return "\n".join(
            [
                f"🔎 Buyurtma: {sn}",
                "_______",
                "",
                _format_line(item),
                "",
                "_______",
            ]
        ).strip()
    return None


def _format_requested_track_fallback(data: Dict[str, Any], track: str) -> str:
    match = find_order_in_data(data, track)
    if match and isinstance(match.get("row"), dict):
        source = str(match.get("source") or "delivery")
        item = normalize_order_row(match["row"], source)
        sn = item.get("sn") or track
        return "\n".join(
            [
                f"🔎 Buyurtma: {sn}",
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
        "Bu buyurtma sizga tegishli emas."
    )


def format_orders_message(data: Dict[str, Any], *, max_per_section: int = _DEFAULT_MAX) -> str:
    if data.get("error"):
        return data.get("message", "Ma'lumot topilmadi.")
    if data.get("ownership_mismatch"):
        return data.get("message", "Bu buyurtma sizga tegishli emas.")

    requested = data.get("requested_track")
    focused = _format_focused_order(data)
    if focused:
        return focused

    if requested:
        return _format_requested_track_fallback(data, str(requested))

    scope = data.get("list_scope")
    lines: List[str] = [
        f"📋 {scope}" if scope else "📋 Buyurtmalaringiz holati",
    ]

    summary = summarize_orders_for_prompt(data, max_per_section=max_per_section)
    sections = summary.get("bolimlar") or {}
    if not sections and not focus:
        return (
            "📭 Aktiv buyurtma topilmadi.\n_______\n"
            "Yaqinda buyurtma qilgan bo'lsangiz, birozdan keyin yozing."
        )

    shown_focus_sn = ""
    order_focus = data.get("order_focus")
    if isinstance(order_focus, dict) and isinstance(order_focus.get("row"), dict):
        shown_focus_sn = order_sn_from_row(order_focus["row"]).upper()
    elif isinstance(data.get("daigou_focus"), dict):
        shown_focus_sn = order_sn_from_row(data["daigou_focus"]).upper()

    for key, block in sections.items():
        title = block.get("sarlavha", "Buyurtmalar")
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
    lines.append("Batafsil: track raqam (DG... yoki TRACK...) yuboring.")
    return "\n".join(lines).strip()


def _coerce_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
