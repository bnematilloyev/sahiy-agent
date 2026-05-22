from __future__ import annotations

from app.domain.order_list_menu import (
    build_order_list_menu_extra,
    needs_order_list_menu,
    parse_order_menu_callback,
)


def test_needs_menu_for_korsat():
    assert needs_order_list_menu("zakazlarimni ko'rsat")
    assert needs_order_list_menu("buyurtmalarimni ko'rmoqchiman")
    assert needs_order_list_menu("buyurtmalarim qayerda")


def test_no_menu_when_specific_filter():
    assert not needs_order_list_menu("bekor buyurtmalarim")
    assert not needs_order_list_menu("aktiv zakazlarim")


def test_no_menu_with_track():
    assert not needs_order_list_menu("TRACK001 qayerda")


def test_callback_maps_to_query():
    assert parse_order_menu_callback("ord_active") == "aktiv buyurtmalarim"
    assert parse_order_menu_callback("ord_daigou") == "xitoydagi daigou buyurtmalarim"
    assert parse_order_menu_callback("pp_r_1") is None


def test_keyboard_has_ord_buttons():
    extra = build_order_list_menu_extra()
    codes = [
        btn["callback_data"]
        for row in extra["inline_keyboard"]
        for btn in row
    ]
    assert "ord_all" in codes
    assert "ord_cancelled" in codes
    assert all(c.startswith("ord_") for c in codes)
