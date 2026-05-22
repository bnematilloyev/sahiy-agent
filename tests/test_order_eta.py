from app.domain.order_eta import (
    estimate_remaining_days,
    format_eta_from_status,
    format_eta_message,
    is_eta_question,
    pick_order_for_eta,
    resolve_logistics_status,
)


def test_is_eta_question():
    assert is_eta_question("Buyurtmam qachon keladi?")
    assert is_eta_question("tovarim necha kunda yetib keladi")
    assert is_eta_question("when will my order arrive")
    assert not is_eta_question("buyurtmalarim qayerda")


def test_logistics_info_current_status():
    row = {
        "status": 4,
        "logistics_info": {
            "current_status": 7,
            "comment": "Order completed",
        },
    }
    assert resolve_logistics_status(row, "delivery") == 7


def test_daigou_fallback_mapping():
    assert resolve_logistics_status({"status": 2}, "daigou") == 2
    assert resolve_logistics_status({"status": 5}, "daigou") == 3


def test_delivery_fallback_mapping():
    assert resolve_logistics_status({"status": 4}, "delivery") == 7
    assert resolve_logistics_status({"status": 7}, "delivery") == 12


def test_estimate_remaining_days_from_status_4():
    # 4..11 inclusive: 4+5+1+1+1+1+2+1+3 = 18
    assert estimate_remaining_days(4) == 18


def test_estimate_remaining_days_from_status_7():
    # 7..11: 1+1+2+1+3 = 8
    assert estimate_remaining_days(7) == 8


def test_estimate_delivered():
    assert estimate_remaining_days(12) == 0


def test_format_eta_uz():
    text = format_eta_from_status(7, "uz_lat")
    assert "Markaziy punktda" in text
    assert "~8 kun" in text


def test_format_eta_delivered():
    text = format_eta_from_status(12, "ru")
    assert "доставлен" in text.lower()


def test_pick_order_for_eta_focus():
    data = {
        "order_focus": {
            "source": "jiyun",
            "row": {"status": 4, "order_sn": "123"},
        }
    }
    row, source = pick_order_for_eta(data)
    assert source == "jiyun"
    assert row["order_sn"] == "123"


def test_format_eta_message_with_logistics_info():
    row = {
        "express_num": "T1",
        "status": 3,
        "logistics_info": {"current_status": 5},
    }
    msg = format_eta_message(row, "delivery", "en")
    assert msg is not None
    assert "Uzbekistan" in msg
    assert "~14 days" in msg
