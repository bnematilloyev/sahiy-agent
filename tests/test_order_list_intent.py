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


def test_parse_tovarim_qachon_keladi_pending_arrival():
    intent = parse_order_list_intent("tovarim qachon keladi")
    assert intent.row_filter == "pending_arrival"
    assert intent.sources == frozenset({"daigou", "jiyun"})


def test_pending_arrival_excludes_completed_and_cancelled():
    delivery = [
        {"order_sn": "A", "status": 7},
        {"order_sn": "B", "status": 2},
        {"order_sn": "C", "status": 8},
    ]
    daigou = [
        {"order_sn": "DG1", "status": 10},
        {"order_sn": "DG2", "status": 6},
        {"order_sn": "DG3", "status": 5},
    ]
    jiyun = [
        {"order_sn": "J1", "status": 5},
        {"order_sn": "J2", "status": 4},
    ]
    assert len(filter_order_rows(delivery, "delivery", "pending_arrival")) == 2
    assert len(filter_order_rows(daigou, "daigou", "pending_arrival")) == 1
    assert filter_order_rows(daigou, "daigou", "pending_arrival")[0]["order_sn"] == "DG3"
    assert len(filter_order_rows(jiyun, "jiyun", "pending_arrival")) == 1


def test_apply_pending_arrival_filters_payload():
    data = {
        "delivery_orders": [
            {"order_sn": "done", "status": 7},
            {"order_sn": "kz", "status": 2},
        ],
        "daigou_orders": [
            {"order_sn": "DG1", "status": 10},
            {"order_sn": "DG2", "status": 6},
            {"order_sn": "DG3", "status": 3},
        ],
        "jiyun_orders": [{"order_sn": "435", "status": 4}],
        "daigou_total": 3,
    }
    intent = parse_order_list_intent("tovarim qachon keladi")
    filtered = apply_list_intent_to_payload(data, intent)
    assert len(filtered["delivery_orders"]) == 1
    assert filtered["delivery_orders"][0]["order_sn"] == "kz"
    assert len(filtered["daigou_orders"]) == 1
    assert filtered["daigou_orders"][0]["order_sn"] == "DG3"
    assert filtered["list_scope"] == "Kutilayotgan buyurtmalar"


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
