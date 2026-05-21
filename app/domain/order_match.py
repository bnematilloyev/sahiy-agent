"""Match a specific track/order_sn inside a customer snapshot."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.domain.order_refs import extract_track

_ORDER_ID_KEYS = (
    "order_sn",
    "express_num",
    "track_number",
    "client_order_sn",
    "logistics_sn",
    "shipment_sn",
    "sn",
)

_SNAPSHOT_SECTIONS: Tuple[Tuple[str, str], ...] = (
    ("unpicked_delivery", "unpicked"),
    ("delivery_orders", "delivery"),
    ("dashboard_orders", "dashboard"),
    ("jiyun_orders", "jiyun"),
    ("daigou_orders", "daigou"),
)


def normalize_track_key(value: str) -> str:
    return re.sub(r"[\s\-_]", "", value.strip()).upper()


def row_matches_track(row: Dict[str, Any], track: str) -> bool:
    target = normalize_track_key(track)
    if not target:
        return False
    for key in _ORDER_ID_KEYS:
        raw = row.get(key)
        if raw is not None and normalize_track_key(str(raw)) == target:
            return True
    return False


def find_order_in_data(data: Dict[str, Any], track: str) -> Optional[Dict[str, Any]]:
    """Return {source, row} if track exists in snapshot payload."""
    for field, source in _SNAPSHOT_SECTIONS:
        rows = data.get(field) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row_matches_track(row, track):
                return {"source": source, "row": row}
    tracking = data.get("tracking")
    if isinstance(tracking, dict) and row_matches_track(tracking, track):
        return {"source": "tracking", "row": tracking}
    focus = data.get("daigou_focus")
    if isinstance(focus, dict) and row_matches_track(focus, track):
        return {"source": "daigou", "row": focus}
    return None


def query_requests_specific_order(query: str) -> bool:
    return extract_track(query) is not None


def snapshot_has_track(data: Dict[str, Any], track: str) -> bool:
    return find_order_in_data(data, track) is not None


def track_focus_is_valid(snapshot: Any, track: str) -> bool:
    """order_focus / daigou_focus must reference the requested track."""
    order_focus = getattr(snapshot, "order_focus", None)
    if isinstance(order_focus, dict):
        row = order_focus.get("row")
        if isinstance(row, dict) and row_matches_track(row, track):
            return True
    daigou_focus = getattr(snapshot, "daigou_focus", None)
    if isinstance(daigou_focus, dict) and row_matches_track(daigou_focus, track):
        return True
    return False
