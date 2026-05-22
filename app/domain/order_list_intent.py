"""Mijoz so'roviga qarab qaysi buyurtma API va qanday filtr ishlatish."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional

from app.domain.order_refs import extract_track, is_order_list_question
from app.domain.text_normalize import normalize_text

_ALL_SOURCES: FrozenSet[str] = frozenset(
    {"delivery", "daigou", "dashboard", "jiyun", "unpicked"}
)

_DAIGOU_KW = (
    "daigou",
    "daigo",
    "dg zakaz",
    "xitoy",
    "xitoyda",
    "xitoydagi",
    "omborda",
    "ombor",
    "sotib olin",
)
_DELIVERY_KW = (
    "yetkazib",
    "yetkazish",
    "delivery",
    "kuryer",
    "pochta",
    "yurt ich",
    "logistika",
)
_UNPICKED_KW = (
    "olib ketilmagan",
    "olib kelmagan",
    "olib kelinmagan",
    "markaziy stansiya",
    "stansiyada",
    "punktga kelmagan",
)
_DASHBOARD_KW = (
    "filialda",
    "punktda",
    "filial punkt",
)
_JIYUN_KW = ("jiyun",)

_CANCELLED_KW = (
    "bekor",
    "bekorlangan",
    "bekor qilingan",
    "bekor bolgan",
    "otmen",
    "cancel",
    "cancelled",
)
_ACTIVE_KW = (
    "aktiv",
    "faol",
    "ochiq",
    "jarayonda",
    "davom et",
)
_COMPLETED_KW = (
    "yakunlangan",
    "tugagan",
    "yetkazilgan",
    "olib ketilgan",
    "qabul qilingan",
)
_DELAYED_KW = (
    "kelmayapti",
    "kelmay",
    "kelmagan",
    "kemayapti",
    "kemay",
    "kemagan",
    "yetkazilmagan",
    "yetkazilmadi",
    "kechik",
)
_IN_CHINA_KW = (
    "xitoyda",
    "xitoydagi",
    "xitoy ombor",
)


def _status_code(row: Dict[str, Any]) -> Optional[int]:
    try:
        v = row.get("status")
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class OrderListIntent:
    """Qaysi manbalarga API chaqirish va qaysi qatorlarni ko'rsatish."""

    sources: FrozenSet[str]
    row_filter: Optional[str] = None  # active | cancelled | completed | delayed | in_china

    @staticmethod
    def default() -> OrderListIntent:
        return OrderListIntent(sources=_ALL_SOURCES, row_filter=None)

    def scope_title(self) -> Optional[str]:
        parts: List[str] = []
        if self.row_filter == "cancelled":
            parts.append("Bekor qilingan buyurtmalar")
        elif self.row_filter == "active":
            parts.append("Aktiv buyurtmalar")
        elif self.row_filter == "completed":
            parts.append("Yakunlangan buyurtmalar")
        elif self.row_filter == "delayed":
            parts.append("Kechikkan / olib ketilmagan")
        elif self.row_filter == "in_china":
            parts.append("Xitoy bosqichidagi buyurtmalar")
        if len(self.sources) == 1:
            only = next(iter(self.sources))
            if only == "daigou" and not parts:
                return "🇨🇳 Daigou (Xitoy omborigacha)"
            if only == "daigou":
                parts.append("(daigou)")
            elif only == "delivery" and not parts:
                return "📦 Yetkazib berish buyurtmalari"
            elif only == "unpicked" and not parts:
                return "⏳ Olib ketilmagan buyurtmalar"
            elif only == "dashboard" and not parts:
                return "📍 Filialdagi buyurtmalar"
        if parts:
            return parts[0]
        if self.row_filter or self.sources != _ALL_SOURCES:
            return "Buyurtmalar"
        return None


def parse_order_list_intent(text: str) -> OrderListIntent:
    lowered = normalize_text(text or "")
    if not lowered:
        return OrderListIntent.default()

    row_filter: Optional[str] = None
    if any(k in lowered for k in _CANCELLED_KW):
        row_filter = "cancelled"
    elif any(k in lowered for k in _DELAYED_KW):
        row_filter = "delayed"
    elif any(k in lowered for k in _IN_CHINA_KW):
        row_filter = "in_china"
    elif any(k in lowered for k in _COMPLETED_KW):
        row_filter = "completed"
    elif any(k in lowered for k in _ACTIVE_KW):
        row_filter = "active"

    sources = set(_ALL_SOURCES)
    want_daigou = any(k in lowered for k in _DAIGOU_KW)
    want_delivery = any(k in lowered for k in _DELIVERY_KW)
    want_unpicked = any(k in lowered for k in _UNPICKED_KW)
    want_dashboard = any(k in lowered for k in _DASHBOARD_KW)
    want_jiyun = any(k in lowered for k in _JIYUN_KW)

    if row_filter == "delayed":
        want_unpicked = True
        want_delivery = True

    if row_filter == "in_china":
        want_daigou = True
        want_delivery = True

    narrowed = want_daigou or want_delivery or want_unpicked or want_dashboard or want_jiyun
    if narrowed:
        sources = set()
        if want_daigou:
            sources.add("daigou")
        if want_delivery:
            sources.add("delivery")
        if want_unpicked:
            sources.add("unpicked")
        if want_dashboard:
            sources.add("dashboard")
        if want_jiyun:
            sources.add("jiyun")
    elif row_filter == "cancelled":
        sources = {"daigou", "jiyun"}
    elif row_filter == "delayed":
        sources = {"delivery", "unpicked"}
    elif row_filter == "in_china":
        sources = {"daigou", "delivery"}

    return OrderListIntent(sources=frozenset(sources), row_filter=row_filter)


def should_fetch_with_list_intent(query: str, *, track: Optional[str]) -> bool:
    """Track bo'yicha qidiruvda to'liq snapshot kerak; ro'yxat/so'rovda intent."""
    if track and not is_order_list_question(query):
        return False
    intent = parse_order_list_intent(query)
    if intent != OrderListIntent.default():
        return True
    return is_order_list_question(query)


def _row_matches_filter(row: Dict[str, Any], source: str, row_filter: str) -> bool:
    code = _status_code(row)
    dash = row.get("dashboard_status")
    try:
        dash_code = int(dash) if dash is not None else None
    except (TypeError, ValueError):
        dash_code = None

    if row_filter == "cancelled":
        if source == "daigou":
            return code in (10, 11)
        return False

    if row_filter == "completed":
        if source == "delivery":
            return code == 7
        if source == "daigou":
            return code in (6, 7) if code is not None else False
        if source == "dashboard":
            return dash_code in (2, 3, 4, 5, 6, 7) if dash_code is not None else False
        if source == "jiyun":
            return code == 5
        return False

    if row_filter == "active":
        if source == "daigou":
            return code not in (10, 11) if code is not None else True
        if source == "delivery":
            return code != 7 if code is not None else True
        if source == "unpicked":
            return True
        if source == "dashboard":
            from app.infrastructure.sahiy_api.status_maps import is_unpicked_dashboard

            return is_unpicked_dashboard(dash_code)
        if source == "jiyun":
            return code not in (5,) if code is not None else True
        return True

    if row_filter == "delayed":
        if source == "unpicked":
            return True
        if source == "delivery":
            return code == 4 or bool(row.get("possibly_delayed"))
        return False

    if row_filter == "in_china":
        if source == "delivery":
            return code in (1, 2)
        if source == "daigou":
            return code in (0, 1, 2, 3, 4, 5, 6) if code is not None else True
        return False

    return True


def filter_order_rows(
    rows: List[Dict[str, Any]],
    source: str,
    row_filter: Optional[str],
) -> List[Dict[str, Any]]:
    if not row_filter:
        return rows
    return [r for r in rows if isinstance(r, dict) and _row_matches_filter(r, source, row_filter)]


def apply_list_intent_to_payload(data: Dict[str, Any], intent: OrderListIntent) -> Dict[str, Any]:
    """Snapshot dict ustida manba va holat filtri."""
    out = dict(data)
    mapping = {
        "delivery": "delivery_orders",
        "daigou": "daigou_orders",
        "dashboard": "dashboard_orders",
        "jiyun": "jiyun_orders",
        "unpicked": "unpicked_delivery",
    }
    for src, key in mapping.items():
        if src not in intent.sources:
            out[key] = []
            if key == "daigou_orders":
                out["daigou_total"] = 0
            continue
        rows = out.get(key) or []
        if isinstance(rows, list) and intent.row_filter:
            filtered = filter_order_rows(rows, src if src != "unpicked" else "unpicked", intent.row_filter)
            out[key] = filtered
            if key == "daigou_orders":
                out["daigou_total"] = len(filtered)
    title = intent.scope_title()
    if title:
        out["list_scope"] = title
    return out
