"""Order chain dedup va Telegram guruh xabarlari."""

from __future__ import annotations

from app.domain.order_list_intent import apply_list_intent_to_payload, parse_order_list_intent
from app.domain.order_chain import build_order_chain
from app.domain.order_telegram_present import build_order_telegram_messages


def _sample_payload():
    return {
        "daigou_orders": [
            {"order_sn": "DG60376203", "status": 6, "area_name": "Navoiy"},
            {"order_sn": "DG60411111", "status": 3, "area_name": "Navoiy"},
        ],
        "daigou_total": 2,
        "jiyun_orders": [
            {"order_sn": "435147294520990", "status": 4, "updated_at": "2026-05-10"},
            {"order_sn": "773402738804490", "status": 5, "updated_at": "2026-02-17"},
        ],
        "delivery_orders": [
            {
                "express_num": "435147294520990",
                "status": 8,
                "payment_fee": 300,
                "location_number": "city burchak",
            },
            {"express_num": "773402738804490", "status": 7},
        ],
        "unpicked_delivery": [
            {
                "express_num": "P777180526409",
                "status": 4,
                "location_number": "may 2",
            },
        ],
    }


def test_daigou_status_6_excluded_when_jiyun_exists():
    intent = parse_order_list_intent("tovarim qachon keladi")
    filtered = apply_list_intent_to_payload(_sample_payload(), intent)
    chain = filtered.get("order_chain") or []
    china = next((s for s in chain if s["key"] == "china_purchase"), None)
    assert china is not None
    tracks = [i["track"] for i in china["items"]]
    assert "DG60376203" not in tracks
    assert "DG60411111" in tracks


def test_pending_arrival_two_sections_only():
    intent = parse_order_list_intent("tovarim qachon keladi")
    assert intent.sources == frozenset({"daigou", "jiyun"})
    filtered = apply_list_intent_to_payload(_sample_payload(), intent)
    keys = [s["key"] for s in filtered.get("order_chain") or []]
    assert keys == ["china_purchase", "in_transit"]


def test_jiyun_enriched_with_delivery_branch():
    intent = parse_order_list_intent("tovarim qachon keladi")
    filtered = apply_list_intent_to_payload(_sample_payload(), intent)
    transit = next(s for s in filtered["order_chain"] if s["key"] == "in_transit")
    item = next(i for i in transit["items"] if i["track"] == "435147294520990")
    assert any("city burchak" in e for e in item["extras"])
    assert any("300" in e for e in item["extras"])


def test_telegram_messages_are_separate():
    intent = parse_order_list_intent("tovarim qachon keladi")
    data = apply_list_intent_to_payload(_sample_payload(), intent)
    data["list_scope"] = "Kutilayotgan buyurtmalar"
    messages = build_order_telegram_messages(data, lang="uz_lat")
    assert len(messages) >= 3
    assert messages[0].startswith("📋")
    assert "🇨🇳" in messages[1]
    assert "🚚" in messages[2]
    assert "💡" in messages[-1]


def test_active_orders_english_use_chain():
    intent = parse_order_list_intent("where is my active orders")
    data = apply_list_intent_to_payload(_sample_payload(), intent)
    assert data.get("use_order_chain") is True
    keys = [s["key"] for s in data.get("order_chain") or []]
    assert "delivery_orders" not in data or not data.get("delivery_orders")
    assert keys == ["china_purchase", "in_transit"]
    transit = next(s for s in data["order_chain"] if s["key"] == "in_transit")
    tracks = [i["track"] for i in transit["items"]]
    assert "773402738804490" not in tracks
    assert "435147294520990" in tracks


def test_build_order_chain_skipped_for_cancelled_intent():
    intent = parse_order_list_intent("bekor buyurtmalarim")
    sections = build_order_chain(_sample_payload(), intent)
    assert sections == []
