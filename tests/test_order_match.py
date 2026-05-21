from __future__ import annotations

from app.domain.order_match import find_order_in_data, row_matches_track
from app.domain.order_present import format_orders_message


def test_row_matches_express_num():
    row = {"express_num": "773402738804490", "status": 7}
    assert row_matches_track(row, "773402738804490")


def test_find_in_snapshot_payload():
    data = {
        "delivery_orders": [
            {"express_num": "773402738804490", "status": 7, "updated_at": "2026-02-17"},
        ],
    }
    match = find_order_in_data(data, "773402738804490")
    assert match is not None
    assert match["source"] == "delivery"


def test_format_requested_track_not_in_list_shows_mismatch():
    data = {
        "user_id": 5,
        "requested_track": "773402939631585",
        "delivery_orders": [{"express_num": "OTHER", "status": 7}],
    }
    text = format_orders_message(data)
    assert "773402939631585" in text
    assert "tegishli emas" in text
    assert "Buyurtmalaringiz holati" not in text


def test_format_ownership_mismatch():
    data = {
        "error": "ownership_mismatch",
        "ownership_mismatch": True,
        "message": "🔎 773402939631585\n_______\nBu buyurtma sizga tegishli emas.",
    }
    text = format_orders_message(data)
    assert "tegishli emas" in text
    assert "Buyurtmalaringiz holati" not in text


def test_format_focused_only_one_order():
    data = {
        "user_id": 1,
        "order_focus": {
            "source": "delivery",
            "row": {
                "express_num": "773402738804490",
                "status": 7,
                "updated_at": "2026-02-17T00:00:00Z",
            },
        },
        "delivery_orders": [
            {"express_num": "773402738804490", "status": 7},
            {"express_num": "OTHER", "status": 1},
        ],
    }
    text = format_orders_message(data)
    assert "773402738804490" in text
    assert "So'ralgan" in text or "Buyurtma:" in text
    assert "OTHER" not in text
    assert "Buyurtmalaringiz holati" not in text
