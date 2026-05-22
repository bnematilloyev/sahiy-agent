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
    "daigou", "daigo", "dg zakaz",
    "xitoy", "xitoyda", "xitoydagi", "omborda", "ombor", "sotib olin",
    # RU
    "kitai", "kitajskij", "sklad kitai", "zakup", "skupka",
)
_DELIVERY_KW = (
    "yetkazib", "yetkazish", "delivery", "kuryer", "pochta", "yurt ich", "logistika",
    # RU
    "dostavka", "kuryer", "pochta",
)
_UNPICKED_KW = (
    "olib ketilmagan", "olib kelmagan", "olib kelinmagan",
    "markaziy stansiya", "stansiyada", "punktga kelmagan",
    # RU
    "ne polucheno", "ne zabral", "ne zabrana", "zhdet v punkete",
)
_DASHBOARD_KW = (
    "filialda", "punktda", "filial punkt",
    # RU
    "v filiale", "v punkte",
)
_JIYUN_KW = ("jiyun",)

_CANCELLED_KW = (
    "bekor", "bekorlangan", "bekor qilingan", "bekor bolgan",
    "otmen", "cancel", "cancelled",
    # RU (Cyrillic will be transliterated by normalize_text)
    "otmen", "otmenyon", "otmenennye", "otmena", "otmenili",
)
_ACTIVE_KW = (
    "aktiv", "faol", "ochiq", "jarayonda", "davom et",
    # RU
    "aktiv", "aktivny", "aktivnye", "tekushchie", "otkryt",
)
_COMPLETED_KW = (
    "yakunlangan", "tugagan", "yetkazilgan", "olib ketilgan", "qabul qilingan",
    # RU
    "zavershyon", "zavershenye", "poluchennye", "poluchil", "zakryt",
)
_DELAYED_KW = (
    "kelmayapti", "kelmay", "kelmagan", "kemayapti", "kemay", "kemagan",
    "yetkazilmagan", "yetkazilmadi", "kechik",
    # RU
    "ne prishel", "ne priehalo", "zaderzhka", "zaderzhalas", "opozdanie",
)
_IN_CHINA_KW = (
    "xitoyda", "xitoydagi", "xitoy ombor",
    # RU
    "v kitae", "iz kitaya", "kitajskij sklad",
)
_ARRIVAL_KW = (
    "qachon keladi",
    "qachon kelad",
    "qachon yetkaziladi",
    "qachon yetib keladi",
    "qachon olaman",
    "qachon boradi",
    "qachon priydet",
    "kogda pridet",
    "kogda priydet",
    "when will it arrive",
    "when will my order arrive",
    "when will my package arrive",
)
_ARRIVAL_CONTEXT = (
    "tovar",
    "tovarim",
    "tovarlar",
    "zakaz",
    "zakazim",
    "buyurtma",
    "buyurtmam",
    "posylk",
    "mahsulot",
    "moi tovar",
    "moi zakaz",
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
    row_filter: Optional[str] = None  # active | pending_arrival | cancelled | completed | delayed | in_china

    @staticmethod
    def default() -> OrderListIntent:
        return OrderListIntent(sources=_ALL_SOURCES, row_filter=None)

    def scope_title(self, lang: str = "uz_lat") -> Optional[str]:
        _FILTER_TITLES = {
            "cancelled": {
                "uz_lat": "Bekor qilingan buyurtmalar",
                "uz_cyrl": "Бекор қилинган буюртмалар",
                "ru": "Отменённые заказы",
                "en": "Cancelled orders",
                "zh": "已取消订单",
            },
            "active": {
                "uz_lat": "Aktiv buyurtmalar",
                "uz_cyrl": "Актив буюртмалар",
                "ru": "Активные заказы",
                "en": "Active orders",
                "zh": "活跃订单",
            },
            "pending_arrival": {
                "uz_lat": "Kutilayotgan buyurtmalar",
                "uz_cyrl": "Кutilayotgan буюртмалар",
                "ru": "Заказы в пути",
                "en": "Orders on the way",
                "zh": "在途订单",
            },
            "completed": {
                "uz_lat": "Yakunlangan buyurtmalar",
                "uz_cyrl": "Якунланган буюртмалар",
                "ru": "Завершённые заказы",
                "en": "Completed orders",
                "zh": "已完成订单",
            },
            "delayed": {
                "uz_lat": "Kechikkan / olib ketilmagan",
                "uz_cyrl": "Кечикқан / олиб кетилмаган",
                "ru": "Задержанные / не полученные",
                "en": "Delayed / not picked up",
                "zh": "延迟/未取货",
            },
            "in_china": {
                "uz_lat": "Xitoy bosqichidagi buyurtmalar",
                "uz_cyrl": "Хитой босқичидаги буюртмалар",
                "ru": "Заказы на этапе Китая",
                "en": "Orders in China stage",
                "zh": "中国阶段订单",
            },
        }
        _SOURCE_ONLY_TITLES = {
            "daigou": {
                "uz_lat": "🇨🇳 Daigou (Xitoy omborigacha)",
                "uz_cyrl": "🇨🇳 Daigou (Хитой омборигача)",
                "ru": "🇨🇳 Daigou (до склада в Китае)",
                "en": "🇨🇳 Daigou (to China warehouse)",
                "zh": "🇨🇳 代购（至中国仓库）",
            },
            "delivery": {
                "uz_lat": "📦 Yetkazib berish buyurtmalari",
                "uz_cyrl": "📦 Етказиб бериш буюртмалари",
                "ru": "📦 Заказы доставки",
                "en": "📦 Delivery orders",
                "zh": "📦 配送订单",
            },
            "unpicked": {
                "uz_lat": "⏳ Olib ketilmagan buyurtmalar",
                "uz_cyrl": "⏳ Олиб кетилмаган буюртмалар",
                "ru": "⏳ Не полученные заказы",
                "en": "⏳ Awaiting pickup orders",
                "zh": "⏳ 待取货订单",
            },
            "dashboard": {
                "uz_lat": "📍 Filialdagi buyurtmalar",
                "uz_cyrl": "📍 Филиалдаги буюртмалар",
                "ru": "📍 Заказы в филиале",
                "en": "📍 Branch orders",
                "zh": "📍 分支机构订单",
            },
        }
        _FALLBACK = {
            "uz_lat": "Buyurtmalar",
            "uz_cyrl": "Буюртмалар",
            "ru": "Заказы",
            "en": "Orders",
            "zh": "订单",
        }

        def _pick(d: dict) -> str:
            return d.get(lang) or d.get("uz_lat", "")

        parts: List[str] = []
        if self.row_filter and self.row_filter in _FILTER_TITLES:
            parts.append(_pick(_FILTER_TITLES[self.row_filter]))

        if len(self.sources) == 1:
            only = next(iter(self.sources))
            if only in _SOURCE_ONLY_TITLES and not parts:
                return _pick(_SOURCE_ONLY_TITLES[only])
            if only == "daigou" and parts:
                parts.append("(daigou)")

        if parts:
            return parts[0]
        if self.row_filter or self.sources != _ALL_SOURCES:
            return _pick(_FALLBACK)
        return None


def _is_pending_arrival_question(lowered: str) -> bool:
    if any(k in lowered for k in _ARRIVAL_KW):
        return True
    if not any(w in lowered for w in ("qachon", "kogda", "when")):
        return False
    if not any(w in lowered for w in ("keladi", "kelad", "pridet", "priydet", "arrive", "yetkaz")):
        return False
    return any(w in lowered for w in _ARRIVAL_CONTEXT)


def parse_order_list_intent(text: str) -> OrderListIntent:
    lowered = normalize_text(text or "")
    if not lowered:
        return OrderListIntent.default()

    row_filter: Optional[str] = None
    if any(k in lowered for k in _CANCELLED_KW):
        row_filter = "cancelled"
    elif any(k in lowered for k in _DELAYED_KW):
        row_filter = "delayed"
    elif _is_pending_arrival_question(lowered):
        row_filter = "pending_arrival"
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

    if row_filter in ("active", "pending_arrival"):
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


def apply_list_intent_to_payload(
    data: Dict[str, Any], intent: OrderListIntent, lang: str = "uz_lat"
) -> Dict[str, Any]:
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
    title = intent.scope_title(lang)
    if title:
        out["list_scope"] = title
    return out
