from __future__ import annotations

from app.domain.customer_identity import (
    extract_registration_phone,
    extract_sahiy_user_id,
    is_identity_only_message,
    sahiy_phone_search_candidates,
    validate_uzbek_phone,
)
from app.domain.order_refs import extract_track


def test_validate_uzbek_phone():
    assert validate_uzbek_phone("998901234567") == "998901234567"
    assert validate_uzbek_phone("+998 90 123 45 67") == "998901234567"
    assert validate_uzbek_phone("901234567") == "998901234567"
    assert validate_uzbek_phone("12345") is None
    assert validate_uzbek_phone("773402738804490") is None


def test_extract_registration_phone():
    assert extract_registration_phone("998901234567") == "998901234567"
    assert extract_registration_phone("telefon 998901234567") == "998901234567"
    assert extract_registration_phone("track 773402738804490") is None


def test_track_not_confused_with_phone():
    assert extract_track("998901234567") is None
    assert extract_track("773402738804490") == "773402738804490"


def test_extract_sahiy_user_id():
    assert extract_sahiy_user_id("111111") == 111111
    assert extract_sahiy_user_id("id 191052") == 191052
    assert extract_sahiy_user_id("773402738804490") is None
    assert extract_sahiy_user_id("337255544") is None


def test_legacy_phone_candidates():
    assert "337255544" in sahiy_phone_search_candidates("337255544")
    assert "998337255544" in sahiy_phone_search_candidates("337255544")


def test_identity_only_message():
    assert is_identity_only_message("111111")
    assert is_identity_only_message("id 191052")
    assert not is_identity_only_message("111111 buyurtmam qayerda")
