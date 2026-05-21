from __future__ import annotations

from app.domain.order_refs import (
    build_order_query_text,
    extract_phone,
    extract_track,
    is_daigou_sn,
    is_order_list_question,
    is_order_lookup_request,
)


def test_dg_and_prefixed_tracks():
    assert extract_track("Meni DG123456 zakazim qayerda") == "DG123456"
    assert is_daigou_sn("DG123456")
    assert extract_track("TRACKawdawdawdssawda001 zakazim qayerda") == "TRACKAWDAWDAWDSSAWDA001"


def test_long_numeric_is_track_not_phone():
    assert extract_track("773402939631585 bu zakazim qayerda") == "773402939631585"
    assert extract_phone("773402939631585 bu zakazim qayerda") is None


def test_zakazlarim_not_extracted_as_track():
    assert extract_track("zakazlarim qayda") is None
    assert is_order_list_question("zakazlarim qayda")


def test_labeled_track_after_zakaz_word():
    assert extract_track("zakaz raqam DG60353352") == "DG60353352"


def test_order_lookup_kelmayapti():
    assert is_order_lookup_request("Buyurtmam kelmayapti")
    assert is_order_lookup_request("435147294520990 Tovar siniq kelgan vozvrat bormi")


def test_hyphenated_express_track():
    assert extract_track("track raqam Botir-test-101") == "Botir-test-101"
    assert extract_track("Botir-test-101 bu chi") == "Botir-test-101"
