from __future__ import annotations

from app.domain.order_list_intent import (
    OrderListIntent,
    apply_list_intent_to_payload,
    filter_order_rows,
    parse_order_list_intent,
)
from app.domain.order_present import format_orders_message


def test_parse_bekor_only_daigou_sources():
    intent = parse_order_list_intent("bekor bolgan buyurtmalarim")
    assert intent.row_filter == "cancelled"
    assert intent.sources == frozenset({"daigou", "jiyun"})


def test_parse_daigou_xitoy_narrow_source():
    intent = parse_order_list_intent("xitoydagi daigou zakazlarim")
    assert "daigou" in intent.sources
    assert "delivery" not in intent.sources or intent.row_filter == "in_china"


def test_parse_delivery_only():
    intent = parse_order_list_intent("yetkazib berishdagi buyurtmalarim")
    assert intent.sources == frozenset({"delivery"})


def test_parse_aktiv_filter():
    intent = parse_order_list_intent("aktiv buyurtmalarim qayerda")
    assert intent.row_filter == "active"


def test_filter_cancelled_daigou():
    rows = [
        {"order_sn": "DG1", "status": 10},
        {"order_sn": "DG2", "status": 2},
    ]
    out = filter_order_rows(rows, "daigou", "cancelled")
    assert len(out) == 1
    assert out[0]["order_sn"] == "DG1"


def test_apply_list_scope_in_message():
    data = {
        "daigou_orders": [{"order_sn": "DG1", "status": 10}],
        "daigou_total": 1,
    }
    intent = parse_order_list_intent("bekor buyurtmalarim")
    filtered = apply_list_intent_to_payload(data, intent)
    text = format_orders_message(filtered)
    assert "Bekor" in text


def test_default_intent_all_sources():
    assert parse_order_list_intent("buyurtmalarim qayerda") == OrderListIntent.default()
