from __future__ import annotations

from app.core.prompts import extract_user_message, wrap_user_message


def test_wrap_and_extract_roundtrip():
    original = "Buyurtmam qayerda?"
    wrapped = wrap_user_message(original)
    assert extract_user_message(wrapped) == original


def test_extract_legacy_xabar_format():
    assert extract_user_message("Xabar: Yetkazib berish qancha vaqt oladi?") == (
        "Yetkazib berish qancha vaqt oladi?"
    )
