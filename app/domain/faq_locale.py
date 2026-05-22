"""FAQ ko'p tilli matn — DB, seed, mijoz javob tili."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Mapping, Optional, Tuple

from app.domain.entities import FAQEntry
from app.domain.reply_language import RU, UZ_CYRL, UZ_LAT

_I18N_QUESTION_KEYS = (
    ("question_uz", "answer_uz"),
    ("question_cyr", "answer_cyr"),
    ("question_ru", "answer_ru"),
    ("question_en", "answer_en"),
    ("question_zh", "answer_zh"),
)

_LANG_TO_KEYS: dict[str, tuple[str, str]] = {
    UZ_LAT: ("question_uz", "answer_uz"),
    UZ_CYRL: ("question_cyr", "answer_cyr"),
    RU: ("question_ru", "answer_ru"),
    "en": ("question_en", "answer_en"),
    "zh": ("question_zh", "answer_zh"),
}


def normalize_faq_seed_item(item: Mapping[str, Any]) -> Dict[str, Any]:
    """Eski {question, answer} yoki yangi {question_uz, ...} → bitta shakl."""
    if item.get("question_uz"):
        q_uz = str(item["question_uz"]).strip()
        a_uz = str(item.get("answer_uz") or "").strip()
    else:
        q_uz = str(item.get("question") or "").strip()
        a_uz = str(item.get("answer") or "").strip()

    out: Dict[str, Any] = {
        "id": int(item["id"]),
        "category": str(item.get("category") or "general"),
        "question": q_uz,
        "answer": a_uz,
        "question_uz": q_uz,
        "answer_uz": a_uz,
    }
    for qk, ak in _I18N_QUESTION_KEYS:
        if qk == "question_uz":
            continue
        qv = item.get(qk)
        av = item.get(ak)
        out[qk] = str(qv).strip() if qv else None
        out[ak] = str(av).strip() if av else None
    return out


def faq_embed_text(item: Mapping[str, Any]) -> str:
    """Vektor qidiruv — barcha tillardagi savollarni birlashtirish."""
    normalized = normalize_faq_seed_item(item)
    seen: set[str] = set()
    parts: list[str] = []
    for qk, _ in _I18N_QUESTION_KEYS:
        text = normalized.get(qk)
        if not text or text in seen:
            continue
        seen.add(text)
        parts.append(text)
    return " | ".join(parts) if parts else normalized["question_uz"]


def pick_faq_qa(
    entry: FAQEntry,
    reply_language: str,
) -> Tuple[str, str]:
    """Mijoz tiliga mos savol/javob; bo'lmasa o'zbek lotin."""
    lang = reply_language or UZ_LAT
    q_key, a_key = _LANG_TO_KEYS.get(lang, _LANG_TO_KEYS[UZ_LAT])

    q = _get_i18n_field(entry, q_key) or entry.question
    a = _get_i18n_field(entry, a_key) or entry.answer

    if lang == UZ_CYRL and not _get_i18n_field(entry, q_key):
        q = _get_i18n_field(entry, "question_uz") or q
        a = _get_i18n_field(entry, "answer_uz") or a
    elif lang in (RU, "en", "zh") and not _get_i18n_field(entry, q_key):
        q = _get_i18n_field(entry, "question_uz") or q
        a = _get_i18n_field(entry, "answer_uz") or a

    return q.strip(), a.strip()


def faq_entry_for_language(entry: FAQEntry, reply_language: str) -> FAQEntry:
    q, a = pick_faq_qa(entry, reply_language)
    return replace(entry, question=q, answer=a)


def _get_i18n_field(entry: FAQEntry, key: str) -> Optional[str]:
    value = getattr(entry, key, None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def apply_i18n_to_model(model: Any, item: Mapping[str, Any]) -> None:
    """ORM modelga seed yozish."""
    normalized = normalize_faq_seed_item(item)
    model.question = normalized["question_uz"]
    model.answer = normalized["answer_uz"]
    model.category = normalized["category"]
    for key in (
        "question_uz",
        "answer_uz",
        "question_cyr",
        "answer_cyr",
        "question_ru",
        "answer_ru",
        "question_en",
        "answer_en",
        "question_zh",
        "answer_zh",
    ):
        setattr(model, key, normalized.get(key))
