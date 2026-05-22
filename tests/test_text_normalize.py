from __future__ import annotations

from app.domain.keywords import classify_by_keywords
from app.domain.order_refs import is_order_list_question, is_order_lookup_request
from app.domain.text_normalize import normalize_text, transliterate_cyrillic_to_latin


def test_uzbek_cyrillic_tovar_qachon():
    raw = "Товарим қачон келади"
    assert transliterate_cyrillic_to_latin(raw) == "tovarim qachon keladi"
    assert is_order_lookup_request(raw)


def test_uzbek_cyrillic_tovarlar_list():
    raw = "Нима товарлар олганман"
    assert "tovarlar" in normalize_text(raw)
    assert is_order_list_question(raw)


def test_uzbek_cyrillic_malumot():
    raw = "Нима маълумот бор"
    norm = normalize_text(raw)
    assert "nima" in norm
    assert "malumot" in norm or "ma'lumot" in norm


def test_russian_zakaz_gde():
    raw = "Где мой заказ"
    norm = normalize_text(raw)
    assert "gde" in norm
    assert "zakaz" in norm
    assert is_order_lookup_request(raw) or classify_by_keywords(raw) == "api"


def test_russian_kogda():
    raw = "Когда придет товар"
    norm = normalize_text(raw)
    assert "kogda" in norm
    assert "pridet" in norm
