from __future__ import annotations

from app.domain.product_search_intent import is_product_search_intent


def test_lego_need_triggers_search():
    assert is_product_search_intent("menga lego o'yinchog'i kerak edi")


def test_english_books_availability():
    assert is_product_search_intent("kitob ham sotiladimi inglizcha ?")


def test_order_status_not_product_search():
    assert not is_product_search_intent("Meni aktiv buyurtmalarim qayerda")


def test_pickup_not_product_search():
    assert not is_product_search_intent("Navoiyda filiallariz bormi ?")


def test_other_product_types():
    assert is_product_search_intent("boshqa tovar turi bormi")
