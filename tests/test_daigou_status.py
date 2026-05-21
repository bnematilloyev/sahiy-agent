from __future__ import annotations

from app.domain.order_present import format_orders_message, normalize_order_row
from app.infrastructure.sahiy_api.status_maps import daigou_label


def test_daigou_status_labels():
    assert daigou_label(0) == "To'lov kutilmoqda"
    assert daigou_label(2) == "Sotib olinmoqda"
    assert daigou_label(5) == "Sklatda"
    assert daigou_label(6) == "Yo'lda"


def test_daigou_row_uses_order_sn():
    row = {"order_sn": "DG60353352", "status": 2, "area_name": "Navoiy shahri"}
    item = normalize_order_row(row, "daigou")
    assert item["sn"] == "DG60353352"
    assert item["holat"] == "Sotib olinmoqda"
    assert "Navoiy" in item["joy"]


def test_format_with_daigou_focus():
    data = {
        "daigou_focus": {"order_sn": "DG111", "status": 5, "area_name": "Toshkent"},
        "daigou_orders": [{"order_sn": "DG111", "status": 5}],
        "daigou_total": 1,
    }
    text = format_orders_message(data)
    assert "DG111" in text
    assert "Sklatda" in text
    assert "Xitoy omborigacha" in text
