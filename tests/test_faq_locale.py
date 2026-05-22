from __future__ import annotations

from app.domain.entities import FAQEntry
from app.domain.faq_locale import (
    faq_embed_text,
    faq_entry_for_language,
    normalize_faq_seed_item,
    pick_faq_qa,
)
from app.domain.reply_language import RU, UZ_CYRL, UZ_LAT


def test_normalize_legacy_item():
    row = normalize_faq_seed_item(
        {"id": 3, "category": "x", "question": "Savol?", "answer": "Javob."}
    )
    assert row["question_uz"] == "Savol?"
    assert row["question_ru"] is None


def test_pick_russian():
    entry = FAQEntry(
        id=1,
        question="uz q",
        answer="uz a",
        category="delivery",
        question_uz="uz q",
        answer_uz="uz a",
        question_ru="ru q",
        answer_ru="ru a",
    )
    q, a = pick_faq_qa(entry, RU)
    assert q == "ru q"
    assert a == "ru a"


def test_pick_cyrillic_fallback_to_uz():
    entry = FAQEntry(
        id=1,
        question="uz q",
        answer="uz a",
        category="delivery",
        question_uz="uz q",
        answer_uz="uz a",
        question_cyr=None,
        answer_cyr=None,
    )
    loc = faq_entry_for_language(entry, UZ_CYRL)
    assert loc.question == "uz q"


def test_embed_text_multilingual():
    item = normalize_faq_seed_item(
        {
            "id": 1,
            "category": "d",
            "question_uz": "Q uz",
            "answer_uz": "A",
            "question_ru": "Q ru",
            "answer_ru": "A ru",
        }
    )
    text = faq_embed_text(item)
    assert "Q uz" in text
    assert "Q ru" in text
