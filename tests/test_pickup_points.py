from __future__ import annotations

from app.domain.entities import Message
from app.domain.enums import MessageRole
from app.domain.pickup_keywords import (
    is_order_status_question,
    is_pickup_conversation_turn,
    is_pickup_points_question,
)
from app.domain.pickup_present import has_location_in_text
from app.domain.pickup_present import (
    build_region_keyboard,
    filter_points_by_location_query,
    format_overview,
    parse_callback,
)
from app.infrastructure.sahiy_api.pickup_points import normalize_pickup_point


def test_is_pickup_question():
    assert is_pickup_points_question("Qayerdan olib ketaman?")
    assert is_pickup_points_question("filial qayerda")
    assert is_pickup_points_question("Sahiyning nechta filili qayerlarda bor")
    assert is_pickup_points_question("Navoiyda filiallariz bormi ?")
    assert is_pickup_points_question("Qayerda filiallariz bor?")
    assert not is_pickup_points_question("buyurtmam qayerda")


def test_normalize_pickup_point_uz():
    row = {
        "id": 4,
        "name": {"uz": "City Mall postamati", "en": "x"},
        "address": {"uz": "Toshkent, Botir Zokirov 7"},
        "phone": "555 007 007",
        "type": 2,
        "type_name": "Postamat",
        "region_id": 400930,
        "region_name": "Toshkent shahri",
        "city_name": "Shayxontohur tumani",
    }
    p = normalize_pickup_point(row)
    assert p["name"] == "City Mall postamati"
    assert p["type"] == 2


def test_callback_parse():
    assert parse_callback("pp_r_400930") == ("r", 400930)
    assert parse_callback("pp_t_1") == ("t", 1)


def test_toshkentdachi_location_stem():
    assert has_location_in_text("toshkentdachi ?")
    points = [
        {"type": 1, "region_id": 1, "region_name": "Toshkent shahri", "city_name": "Chilonzor"},
    ]
    matched = filter_points_by_location_query("toshkentdachi ?", points)
    assert len(matched) == 1


def _msg(role: str, content: str) -> Message:
    from datetime import datetime, timezone
    from uuid import uuid4

    return Message(
        id=uuid4(),
        session_id=uuid4(),
        role=role,
        content=content,
        msg_type=None,
        created_at=datetime.now(timezone.utc),
    )


def test_user_id_registration_not_pickup():
    from app.domain.pickup_keywords import (
        is_identity_registration_text,
        is_pickup_conversation_turn,
    )
    from app.domain.pickup_present import has_location_in_text

    msg = "user ID 7991625"
    assert is_identity_registration_text(msg)
    assert not has_location_in_text(msg)
    assert not is_pickup_conversation_turn(msg, [])


def test_complaint_with_track_not_pickup():
    msg = "435147294520990 Tovar siniq kelgan vozvrat bormi"
    from app.domain.pickup_keywords import is_pickup_conversation_turn, is_support_or_order_topic

    recent = [
        _msg(
            MessageRole.ASSISTANT.value,
            "📍 Sahiy topshirish punktlari\nViloyatni tanlang",
        ),
    ]
    assert is_support_or_order_topic(msg)
    assert not is_pickup_conversation_turn(msg, recent)


def test_order_question_not_pickup_even_in_thread():
    recent = [
        _msg(MessageRole.USER.value, "Navoiyda filiallariz bormi ?"),
        _msg(
            MessageRole.ASSISTANT.value,
            "📍 Navoiy\n_______\n\n🏪 Navoiy shahri punkti\nBoshqa viloyat: pastdagi tugmalardan tanlang.",
        ),
    ]
    order_q = "Meni DG123456 zakazim qayerda"
    assert is_order_status_question(order_q)
    assert not has_location_in_text(order_q)
    assert not is_pickup_conversation_turn(order_q, recent)


def test_category_question_exits_pickup_thread():
    from app.domain.pickup_keywords import is_pickup_conversation_turn

    recent = [
        _msg(MessageRole.USER.value, "navoiydagi filial qayerda aynan"),
        _msg(
            MessageRole.ASSISTANT.value,
            "📍 Sahiy topshirish punktlari\n🏪 Filial: 18 ta\nViloyatni tanlang",
        ),
    ]
    assert not is_pickup_conversation_turn(
        "qanday turdagi mahsulot sotasizlar", recent
    )
    assert not is_pickup_conversation_turn("qanday katgoriya", recent)


def test_pickup_followup_in_thread():
    recent = [
        _msg(MessageRole.USER.value, "Navoiyda filiallariz bormi ?"),
        _msg(
            MessageRole.ASSISTANT.value,
            "📍 Navoiy\n_______\n\n🏪 Navoiy shahri punkti\nBoshqa viloyat: pastdagi tugmalardan tanlang.",
        ),
    ]
    assert is_pickup_conversation_turn("toshkentdachi ?", recent)
    assert not is_pickup_points_question("toshkentdachi ?")


def test_filter_by_city_in_question():
    points = [
        {
            "type": 1,
            "region_id": 10,
            "region_name": "Navoiy viloyati",
            "city_name": "Navoiy shahri",
            "name": "Navoiy filiali",
        },
        {
            "type": 1,
            "region_id": 1,
            "region_name": "Toshkent shahri",
            "city_name": "Chilonzor",
            "name": "Toshkent filiali",
        },
    ]
    matched = filter_points_by_location_query("Navoiyda filiallariz bormi?", points)
    assert len(matched) == 1
    assert matched[0]["region_name"] == "Navoiy viloyati"


def test_overview_and_keyboard():
    points = [
        {"type": 1, "region_id": 1, "region_name": "Toshkent shahri"},
        {"type": 2, "region_id": 1, "region_name": "Toshkent shahri"},
        {"type": 1, "region_id": 2, "region_name": "Namangan"},
    ]
    text = format_overview(points)
    assert "Filial" in text
    assert "Postomat" in text
    kb = build_region_keyboard(points)
    assert any(btn["callback_data"].startswith("pp_") for row in kb for btn in row)
