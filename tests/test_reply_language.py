from __future__ import annotations

from app.domain.reply_language import (
    RU,
    UZ_CYRL,
    UZ_LAT,
    detect_reply_language,
    localize,
    resolve_reply_language,
    system_prompt_with_language,
)
from app.core.prompts import RAG_SYSTEM


def test_detect_russian():
    assert detect_reply_language("Где мои товары?") == RU


def test_detect_uzbek_cyrillic():
    assert detect_reply_language("Товарим қачон келади") == UZ_CYRL


def test_detect_uzbek_latin():
    assert detect_reply_language("zakazlarim qayerda") == UZ_LAT


def test_detect_uzbek_not_english_orderlarim():
    assert (
        detect_reply_language("qabul qilgan orderlarim va ularning rasmlari infosi kerak")
        == UZ_LAT
    )


def test_resolve_sticky_from_meta():
    assert (
        resolve_reply_language("ok", {"reply_language": RU}, None) == RU
    )


def test_localize_russian_fallback():
    assert "По этому вопросу" in localize("no_faq_fallback", RU)


def test_system_prompt_includes_russian_instruction():
    prompt = system_prompt_with_language(RAG_SYSTEM, RU)
    assert "русском" in prompt.lower()
