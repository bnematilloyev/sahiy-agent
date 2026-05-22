"""Format pickup points for Telegram (compact text + inline buttons)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.domain.text_normalize import normalize_text

MAX_POINTS_IN_MESSAGE = 8
CALLBACK_PREFIX = "pp"


_LOCATION_SUFFIXES = ("dachi", "dagi", "gacha", "dan", "da", "ga", "chi", "chu")

# Umumiy so'zlar — joy nomi emas (qayerda → qayer xato chiqmasin)
_LOCATION_STOP_TOKENS = frozenset(
    {
        "meni",
        "mening",
        "menga",
        "qayer",
        "qayerda",
        "qayerdan",
        "qayda",
        "zakaz",
        "zakazim",
        "zakazlarim",
        "buyurtma",
        "buyurtmam",
        "buyurtmalar",
        "tovar",
        "tovarim",
        "siniq",
        "singan",
        "kelgan",
        "vozvrat",
        "qaytar",
        "bormi",
        "brak",
        "shikoyat",
        "holat",
        "sahiy",
        "salom",
        "rahmat",
        "track",
        "raqam",
        "user",
        "userid",
        "foydalanuvchi",
    }
)


def has_location_in_text(text: str) -> bool:
    return bool(_location_needles_from_query(text))


def _location_needles_from_query(text: str) -> List[str]:
    """Extract probable place names from phrases like 'Navoiyda filiallariz bormi'."""
    lowered = normalize_text(text)
    needles: List[str] = []
    for token in re.findall(r"[a-zа-яёўқғҳ]+", lowered):
        if len(token) < 4 or re.search(r"\d", token):
            continue
        if token in _LOCATION_STOP_TOKENS:
            continue
        stem = token
        for suffix in _LOCATION_SUFFIXES:
            if stem.endswith(suffix) and len(stem) > len(suffix) + 2:
                stem = stem[: -len(suffix)]
                break
        if len(stem) < 4 or stem in _LOCATION_STOP_TOKENS:
            continue
        if stem not in needles:
            needles.append(stem)
    return needles


def filter_points_by_location_query(
    text: str, points: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    needles = _location_needles_from_query(text)
    if not needles:
        return []

    known: List[str] = []
    for p in points:
        for field in ("region_name", "city_name"):
            val = (p.get(field) or "").strip().lower()
            if val and val not in known:
                known.append(val)

    matched_needles: List[str] = []
    for needle in needles:
        for place in known:
            if needle in place or place.startswith(needle):
                matched_needles.append(needle)
                break

    if not matched_needles:
        return []

    result: List[Dict[str, Any]] = []
    for p in points:
        region = (p.get("region_name") or "").lower()
        city = (p.get("city_name") or "").lower()
        if any(n in region or n in city or region.startswith(n) for n in matched_needles):
            result.append(p)
    return result


def group_by_region(points: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in points:
        region = p.get("region_name") or "Boshqa"
        grouped[region].append(p)
    return dict(grouped)


def count_by_type(points: List[Dict[str, Any]]) -> Tuple[int, int]:
    filial = sum(1 for p in points if p.get("type") == 1)
    postomat = sum(1 for p in points if p.get("type") == 2)
    return filial, postomat


def format_point_line(point: Dict[str, Any]) -> str:
    icon = "🏪" if point.get("type") == 1 else "📮"
    name = point.get("name") or "Punkt"
    tlabel = point.get("type_label") or ""
    city = point.get("city_name") or ""
    address = point.get("address") or ""
    phone = point.get("phone") or ""
    line = f"{icon} {name}"
    if tlabel:
        line += f" ({tlabel})"
    if city or address:
        line += f"\n   {city}"
        if address:
            line += f", {address}"
    if phone:
        line += f"\n   ☎️ {phone}"
    return line


def format_overview(points: List[Dict[str, Any]]) -> str:
    filial, postomat = count_by_type(points)
    lines = [
        "📍 Sahiy topshirish punktlari",
        "",
        f"🏪 Filial: {filial} ta",
        f"📮 Postomat: {postomat} ta",
        "",
        "Viloyatni tanlang yoki turini filtrlang:",
    ]
    return "\n".join(lines)


def format_region_list(region: str, points: List[Dict[str, Any]], *, limit: int = MAX_POINTS_IN_MESSAGE) -> str:
    lines = [f"📍 {region}", "_______", ""]
    for point in points[:limit]:
        lines.append(format_point_line(point))
        lines.append("")
    if len(points) > limit:
        lines.append(f"... yana {len(points) - limit} ta punkt")
    lines.append("_______")
    lines.append("Boshqa viloyat: pastdagi tugmalardan tanlang.")
    return "\n".join(lines).strip()


def format_type_list(label: str, points: List[Dict[str, Any]], *, limit: int = MAX_POINTS_IN_MESSAGE) -> str:
    lines = [f"📍 {label}", "_______", ""]
    for point in points[:limit]:
        lines.append(format_point_line(point))
        lines.append("")
    if len(points) > limit:
        lines.append(f"... yana {len(points) - limit} ta")
    return "\n".join(lines).strip()


def build_region_keyboard(points: List[Dict[str, Any]]) -> List[List[Dict[str, str]]]:
    """Rows of inline buttons for Telegram."""
    regions: Dict[int, str] = {}
    for p in points:
        rid = p.get("region_id")
        rname = p.get("region_name")
        if rid is not None and rname:
            regions[int(rid)] = str(rname)

    sorted_regions = sorted(regions.items(), key=lambda x: x[1])
    rows: List[List[Dict[str, str]]] = []
    row: List[Dict[str, str]] = []
    for rid, rname in sorted_regions[:12]:
        row.append({"text": rname[:32], "callback_data": f"{CALLBACK_PREFIX}_r_{rid}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            {"text": "🏪 Filial", "callback_data": f"{CALLBACK_PREFIX}_t_1"},
            {"text": "📮 Postomat", "callback_data": f"{CALLBACK_PREFIX}_t_2"},
        ]
    )
    return rows


def parse_callback(data: str) -> Optional[Tuple[str, int]]:
    if not data.startswith(f"{CALLBACK_PREFIX}_"):
        return None
    parts = data.split("_")
    if len(parts) < 3:
        return None
    kind, raw_id = parts[1], parts[2]
    if kind not in ("r", "t"):
        return None
    try:
        return kind, int(raw_id)
    except ValueError:
        return None
