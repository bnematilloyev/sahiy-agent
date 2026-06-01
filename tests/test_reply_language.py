from __future__ import annotations

import pytest

from app.domain.reply_language import (
    EN,
    RU,
    UZ_CYRL,
    UZ_LAT,
    detect_reply_language,
    localize,
    resolve_reply_language,
    system_prompt_with_language,
)
from app.core.prompts import RAG_SYSTEM


# ─── Rus kirill ───────────────────────────────────────────────────────────────

def test_detect_russian_vy_prodayote_kurtku():
    """'вы' + 'продаете' — ikkalasi rus so'zlari."""
    assert detect_reply_language("Вы продаете, куртку") == RU


def test_detect_russian_gde_moi_tovary():
    assert detect_reply_language("Где мои товары?") == RU


def test_detect_russian_gde_zakaz():
    assert detect_reply_language("Где мой заказ?") == RU


def test_detect_russian_est_kurtki():
    """'есть' — rus so'zi."""
    assert detect_reply_language("Есть куртки?") == RU


def test_detect_russian_privet():
    assert detect_reply_language("Привет") == RU


def test_detect_russian_exclusive_char_y():
    """'ы' harfi faqat rus kirillida bor."""
    assert detect_reply_language("мы хотим купить") == RU


def test_detect_russian_schch_char():
    """'щ' harfi faqat rus kirillida bor."""
    assert detect_reply_language("ещё раз") == RU


def test_detect_russian_ne_prishel():
    """'мой' rus so'zi."""
    assert detect_reply_language("Мой заказ не пришёл") == RU


def test_detect_russian_kupit():
    assert detect_reply_language("Хочу купить пальто") == RU


def test_detect_russian_dostavka():
    assert detect_reply_language("Сколько стоит доставка?") == RU


# ─── O'zbek kirill ────────────────────────────────────────────────────────────

def test_detect_uzbek_cyrillic_q_char():
    """'қ' faqat o'zbek kirillida."""
    assert detect_reply_language("Товарим қачон келади") == UZ_CYRL


def test_detect_uzbek_cyrillic_bormi():
    assert detect_reply_language("Келмаган товарларим борми") == UZ_CYRL


def test_detect_uzbek_cyrillic_buyurtma():
    assert detect_reply_language("Буюртма") == UZ_CYRL


def test_detect_uzbek_cyrillic_yordам():
    """'Ёрдам' o'zbek so'zi — rus emas."""
    result = detect_reply_language("Ёрдам")
    assert result in (UZ_CYRL, None), f"Expected uz_cyrl or None, got {result!r}"


def test_detect_uzbek_cyrillic_yoki():
    """'ёки' o'zbek so'zi — rus emas."""
    result = detect_reply_language("ёки")
    assert result in (UZ_CYRL, None), f"Expected uz_cyrl or None, got {result!r}"


def test_detect_uzbek_cyrillic_sotasiz():
    assert detect_reply_language("Куртка сотасизми?") == UZ_CYRL


def test_detect_uzbek_cyrillic_nima():
    assert detect_reply_language("нима сотасиз?") == UZ_CYRL


# ─── O'zbek lotin ─────────────────────────────────────────────────────────────

def test_detect_uzbek_latin_zakazlar():
    assert detect_reply_language("zakazlarim qayerda") == UZ_LAT


def test_detect_uzbek_latin_complex():
    assert (
        detect_reply_language("qabul qilgan orderlarim va ularning rasmlari infosi kerak")
        == UZ_LAT
    )


def test_detect_uzbek_latin_salom():
    assert detect_reply_language("salom") == UZ_LAT


# ─── Noaniq / qisqa xabarlar ─────────────────────────────────────────────────

def test_detect_ambiguous_ok_latin():
    """'ok' — noaniq, None qaytarilishi kerak."""
    assert detect_reply_language("ok") is None


def test_detect_ambiguous_ok_cyrillic():
    """'ок' — noaniq, None qaytarilishi kerak."""
    assert detect_reply_language("ок") is None


def test_detect_ambiguous_telefon():
    """'Телефон' ikkala tilda ham bor, aniq signal yo'q."""
    assert detect_reply_language("Телефон") is None


# ─── resolve_reply_language — meta saqlanishi ────────────────────────────────

def test_resolve_russian_detected_overrides_meta():
    """Aniq rus xabari meta'dagi uz_lat ni bekor qiladi."""
    assert resolve_reply_language("Вы продаете, куртку", {"reply_language": UZ_LAT}) == RU


def test_resolve_meta_kept_when_ambiguous():
    """Noaniq xabarda meta tili saqlanadi."""
    assert resolve_reply_language("ok", {"reply_language": RU}) == RU


def test_resolve_meta_kept_when_short_cyrillic():
    """Qisqa noaniq kirill — meta saqlanadi."""
    assert resolve_reply_language("ок", {"reply_language": RU}) == RU


def test_resolve_fallback_to_history():
    """Meta yo'q, history'dan aniqlanadi."""
    from datetime import datetime, timezone
    from uuid import uuid4
    from app.domain.entities import Message

    msg = Message(
        id=uuid4(),
        session_id=uuid4(),
        role="user",
        content="Где мой заказ?",
        msg_type=None,
        created_at=datetime.now(timezone.utc),
    )
    assert resolve_reply_language("ок", None, [msg]) == RU


def test_resolve_default_uz_lat():
    """Hech narsa yo'q — uz_lat."""
    assert resolve_reply_language("ок", None, None) == UZ_LAT


# ─── Lokalizatsiya ────────────────────────────────────────────────────────────

def test_localize_russian_fallback():
    assert "По этому вопросу" in localize("no_faq_fallback", RU)


def test_system_prompt_includes_russian_instruction():
    prompt = system_prompt_with_language(RAG_SYSTEM, RU)
    assert "русском" in prompt.lower()
