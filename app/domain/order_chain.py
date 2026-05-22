"""Duplikatsiz buyurtma zanjiri — daigou (xarid) + jiyun (logistika).

Sahiy ilovasi mantigi:
  • Daigou status 0–5 — Xitoy / xarid bosqichi
  • Daigou status 6+ — jiyun/delivery da ko'rinadi (alohida qator emas)
  • Delivery — alohida ro'yxat emas; jiyun qatoriga filial/to'lov qo'shimchasi
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Set

from app.domain.order_list_intent import OrderListIntent, _ALL_SOURCES
from app.domain.order_match import normalize_track_key
from app.domain.order_present import (
    _format_date,
    _status_code,
    order_sn_from_row,
    status_text,
)
from app.domain.reply_language import UZ_LAT

# Daigou: xarid / Xitoy ombori (6 = jiyun ga o'tgan)
DAIGOU_PURCHASE_STATUSES: FrozenSet[int] = frozenset({0, 1, 2, 3, 4, 5})
DAIGOU_HANDOFF_STATUS = 6


@dataclass(frozen=True)
class OrderChainItem:
    """Bitta mijozga ko'rsatiladigan buyurtma kartochkasi."""

    track: str
    phase: str  # china_purchase | in_transit
    status: str
    date: str
    location: str
    extras: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrderChainSection:
    """Telegram guruh xabari uchun bo'lim."""

    key: str
    items: tuple[OrderChainItem, ...]
    total: int = 0


def should_use_order_chain(intent: Optional[OrderListIntent]) -> bool:
    """Ikki fazali dedup zanjir — tor filtr/intentlarda emas."""
    if intent is None:
        return True
    if intent.row_filter in ("pending_arrival", "active", "completed"):
        return True
    if intent.row_filter is None and intent.sources == _ALL_SOURCES:
        return True
    return False


def enrichment_sources() -> FrozenSet[str]:
    """Jiyun boyitish uchun yashirin fetch manbalari."""
    return frozenset({"delivery", "unpicked", "dashboard"})


def _track_keys_from_row(row: Dict[str, Any]) -> Set[str]:
    keys: Set[str] = set()
    primary = order_sn_from_row(row)
    if primary and primary != "—":
        keys.add(normalize_track_key(primary))
    for field in ("express_num", "track_number", "order_sn", "logistics_sn", "r_order_sn"):
        raw = row.get(field)
        if raw:
            keys.add(normalize_track_key(str(raw)))
    for pkg in row.get("purchase_packages") or []:
        if isinstance(pkg, dict) and pkg.get("express_num"):
            keys.add(normalize_track_key(str(pkg["express_num"])))
    for ex in row.get("expresses") or []:
        if not isinstance(ex, dict):
            continue
        pivot = ex.get("pivot") if isinstance(ex.get("pivot"), dict) else {}
        if pivot.get("express_num"):
            keys.add(normalize_track_key(str(pivot["express_num"])))
        express = ex.get("express") if isinstance(ex.get("express"), dict) else ex
        if isinstance(express, dict) and express.get("express_num"):
            keys.add(normalize_track_key(str(express["express_num"])))
    express = row.get("express")
    if isinstance(express, dict) and express.get("express_num"):
        keys.add(normalize_track_key(str(express["express_num"])))
    return {k for k in keys if k}


def _index_by_track(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in _track_keys_from_row(row):
            out[key] = row
    return out


def _daigou_location(row: Dict[str, Any]) -> str:
    parts = [row.get("area_name"), row.get("sub_area_name")]
    return " — ".join(str(p).strip() for p in parts if p)


def _delivery_branch(row: Dict[str, Any]) -> str:
    loc = row.get("location") if isinstance(row.get("location"), dict) else {}
    branch = (
        row.get("location_number")
        or row.get("branch_name")
        or loc.get("branch_name")
        or loc.get("name")
        or ""
    )
    return str(branch).strip()


def _payment_line(row: Dict[str, Any], lang: str) -> Optional[str]:
    fee = row.get("payment_fee") or row.get("actual_payment_fee")
    if fee is None:
        return None
    try:
        amount = int(float(fee))
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    suffix = "so'm" if lang != "ru" else "сум"
    if lang == "en":
        suffix = "UZS"
    formatted = f"{amount:,}".replace(",", " ")
    labels = {
        "uz_lat": f"To'lov: {formatted} {suffix}",
        "uz_cyrl": f"To'lov: {formatted} {suffix}",
        "ru": f"Oplata: {formatted} {suffix}",
        "en": f"Payment: {formatted} {suffix}",
        "zh": f"付款: {formatted} {suffix}",
    }
    return labels.get(lang) or labels[UZ_LAT]


def _merge_delivery_extras(
    jiyun: Dict[str, Any],
    delivery: Optional[Dict[str, Any]],
    unpicked: Optional[Dict[str, Any]],
    lang: str,
) -> tuple[str, ...]:
    src = unpicked or delivery
    if not src:
        return ()
    pay = _payment_line(src, lang)
    return (pay,) if pay else ()


def _shipped_track_keys(payload: Dict[str, Any]) -> Set[str]:
    keys: Set[str] = set()
    for field in ("jiyun_orders", "delivery_orders", "unpicked_delivery", "dashboard_orders"):
        rows = payload.get(field) or []
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    keys |= _track_keys_from_row(row)
    return keys


def _filter_daigou_purchase(
    rows: List[Dict[str, Any]],
    shipped_keys: Set[str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = _status_code(row)
        if code is not None and code not in DAIGOU_PURCHASE_STATUSES:
            continue
        linked = _track_keys_from_row(row)
        if linked & shipped_keys:
            continue
        out.append(row)
    return out


def _build_transit_items(
    jiyun_rows: List[Dict[str, Any]],
    delivery_idx: Dict[str, Dict[str, Any]],
    unpicked_idx: Dict[str, Dict[str, Any]],
    *,
    lang: str,
    include_completed: bool,
) -> List[OrderChainItem]:
    items: List[OrderChainItem] = []
    seen: Set[str] = set()

    def _append(track: str, tkey: str, row: Dict[str, Any], status_source: str) -> None:
        if tkey in seen:
            return
        code = _status_code(row)
        if not include_completed and code == 7:
            return
        seen.add(tkey)
        delivery = delivery_idx.get(tkey)
        unpicked = unpicked_idx.get(tkey)
        loc = _delivery_branch(unpicked or delivery or row) or _daigou_location(row)
        extras = _merge_delivery_extras(row, delivery, unpicked, lang)
        items.append(
            OrderChainItem(
                track=track,
                phase="in_transit",
                status=status_text(row, status_source, lang),
                date=_format_date(
                    row.get("updated_at") or row.get("shipped_at") or row.get("created_at")
                ),
                location=loc,
                extras=extras,
            )
        )

    for row in jiyun_rows:
        if not isinstance(row, dict):
            continue
        code = _status_code(row)
        if not include_completed and code in (5, 7):
            continue
        track = order_sn_from_row(row)
        if not track or track == "—":
            continue
        _append(track, normalize_track_key(track), row, "jiyun")

    for tkey, row in unpicked_idx.items():
        if not isinstance(row, dict):
            continue
        code = _status_code(row)
        if not include_completed and code in (5, 7):
            continue
        track = order_sn_from_row(row)
        if not track or track == "—":
            continue
        _append(track, tkey, row, "delivery")

    return items


def _build_completed_items(
    jiyun_rows: List[Dict[str, Any]],
    delivery_idx: Dict[str, Dict[str, Any]],
    unpicked_idx: Dict[str, Dict[str, Any]],
    *,
    lang: str,
) -> List[OrderChainItem]:
    """Faqat qabul qilingan: jiyun 5, delivery 7."""
    items: List[OrderChainItem] = []
    seen: Set[str] = set()

    def _append(track: str, tkey: str, row: Dict[str, Any], status_source: str) -> None:
        if tkey in seen:
            return
        code = _status_code(row)
        if status_source == "jiyun" and code != 5:
            return
        if status_source == "delivery" and code != 7:
            return
        seen.add(tkey)
        delivery = delivery_idx.get(tkey)
        unpicked = unpicked_idx.get(tkey)
        loc = _delivery_branch(unpicked or delivery or row) or _daigou_location(row)
        extras = _merge_delivery_extras(row, delivery, unpicked, lang)
        items.append(
            OrderChainItem(
                track=track,
                phase="completed",
                status=status_text(row, status_source, lang),
                date=_format_date(
                    row.get("updated_at") or row.get("shipped_at") or row.get("created_at")
                ),
                location=loc,
                extras=extras,
            )
        )

    for row in jiyun_rows:
        if not isinstance(row, dict):
            continue
        if _status_code(row) != 5:
            continue
        track = order_sn_from_row(row)
        if not track or track == "—":
            continue
        _append(track, normalize_track_key(track), row, "jiyun")

    for tkey, row in delivery_idx.items():
        if not isinstance(row, dict):
            continue
        if _status_code(row) != 7:
            continue
        track = order_sn_from_row(row)
        if not track or track == "—":
            continue
        _append(track, tkey, row, "delivery")

    return items


def build_order_chain(
    payload: Dict[str, Any],
    intent: Optional[OrderListIntent],
    *,
    lang: str = UZ_LAT,
    enrichment: Optional[Dict[str, Any]] = None,
) -> List[OrderChainSection]:
    """Payload dan deduplikatsiya qilingan bo'limlar."""
    if not should_use_order_chain(intent):
        return []

    enrich = enrichment if enrichment is not None else payload
    shipped_keys = _shipped_track_keys(enrich)
    delivery_idx = _index_by_track(list(enrich.get("delivery_orders") or []))
    unpicked_idx = _index_by_track(list(enrich.get("unpicked_delivery") or []))

    include_completed = bool(intent and intent.include_completed)

    if intent and intent.row_filter == "completed":
        completed_items = _build_completed_items(
            list(payload.get("jiyun_orders") or []),
            _index_by_track(list(enrich.get("delivery_orders") or [])),
            _index_by_track(list(enrich.get("unpicked_delivery") or [])),
            lang=lang,
        )
        if completed_items:
            return [
                OrderChainSection(
                    key="completed",
                    items=tuple(completed_items),
                    total=len(completed_items),
                )
            ]
        return []

    daigou_rows = _filter_daigou_purchase(
        list(payload.get("daigou_orders") or []),
        shipped_keys,
    )
    china_items = [
        OrderChainItem(
            track=order_sn_from_row(row),
            phase="china_purchase",
            status=status_text(row, "daigou", lang),
            date=_format_date(row.get("updated_at") or row.get("paid_at") or row.get("created_at")),
            location=_daigou_location(row),
        )
        for row in daigou_rows
        if order_sn_from_row(row) != "—"
    ]

    transit_items = _build_transit_items(
        list(payload.get("jiyun_orders") or []),
        delivery_idx,
        unpicked_idx,
        lang=lang,
        include_completed=include_completed,
    )

    daigou_total = int(payload.get("daigou_total") or len(daigou_rows))
    sections: List[OrderChainSection] = []

    if intent and intent.row_filter in ("pending_arrival", "active"):
        if china_items:
            sections.append(
                OrderChainSection(key="china_purchase", items=tuple(china_items), total=daigou_total)
            )
        if transit_items:
            sections.append(
                OrderChainSection(
                    key="in_transit",
                    items=tuple(transit_items),
                    total=len(transit_items),
                )
            )
        return sections

    if china_items:
        sections.append(
            OrderChainSection(key="china_purchase", items=tuple(china_items), total=daigou_total)
        )
    if transit_items:
        sections.append(
            OrderChainSection(
                key="in_transit",
                items=tuple(transit_items),
                total=len(transit_items),
            )
        )
    return sections


def apply_order_chain_to_payload(
    payload: Dict[str, Any],
    intent: Optional[OrderListIntent],
    *,
    lang: str = UZ_LAT,
    raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Chain bo'limlarini qo'shish. raw — enrichment (delivery/unpicked) uchun to'liq snapshot."""
    if not should_use_order_chain(intent):
        return payload

    enrich_from = raw if raw is not None else payload
    sections = build_order_chain(payload, intent, lang=lang, enrichment=enrich_from)
    out = dict(payload)
    out["order_chain"] = [
        {
            "key": s.key,
            "total": s.total or len(s.items),
            "items": [
                {
                    "track": i.track,
                    "phase": i.phase,
                    "status": i.status,
                    "date": i.date,
                    "location": i.location,
                    "extras": list(i.extras),
                }
                for i in s.items
            ],
        }
        for s in sections
    ]
    out["use_order_chain"] = True
    return out
