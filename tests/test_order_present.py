from __future__ import annotations

from app.domain.order_present import (
    format_orders_message,
    order_sn_from_row,
    summarize_orders_for_prompt,
)


def test_order_sn_prefers_express_num_over_id():
    row = {"id": 78833, "express_num": "TRACK001", "status": 7}
    assert order_sn_from_row(row) == "TRACK001"


def test_summarize_hides_internal_id():
    data = {
        "user_id": 7991625,
        "delivery_orders": [
            {"id": 99, "express_num": "TRACK001", "status": 4, "updated_at": "2026-03-03T10:23:12.000000Z"},
        ],
    }
    summary = summarize_orders_for_prompt(data)
    order = summary["bolimlar"]["delivery_orders"]["buyurtmalar"][0]
    assert "sn" in order
    assert order["sn"] == "TRACK001"
    assert "id" not in order


def test_daigou_section_title():
    data = {
        "daigou_orders": [{"order_sn": "DG1", "status": 2, "area_name": "Toshkent"}],
        "daigou_total": 1,
    }
    text = format_orders_message(data)
    assert "Xitoy omborigacha" in text
    assert "Daigou" not in text


def test_jiyun_section_title_is_buyurtmalar_not_jiyun():
    data = {
        "jiyun_orders": [
            {"order_sn": "435147294520990", "status": 4, "status_name": "已发货"},
        ],
    }
    text = format_orders_message(data)
    assert "Buyurtmalar" in text
    assert "Jiyun" not in text
    assert "Jo'natilgan" in text
    assert "已发货" not in text


def test_format_message_has_separators_and_emoji():
    data = {
        "delivery_orders": [
            {"express_num": "TRACK001", "status": 7, "updated_at": "2026-03-03T10:23:12.000000Z"},
        ],
    }
    text = format_orders_message(data)
    assert "_______" in text
    assert "📦" in text
    assert "TRACK001" in text
    assert "78833" not in text
