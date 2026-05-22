"""O'zbek lotin ↔ kirill (FAQ tarjima uchun)."""

from __future__ import annotations

import re

_LATIN_MULTI: tuple[tuple[str, str], ...] = (
    ("sh", "ш"),
    ("ch", "ч"),
    ("ng", "нг"),
    ("yo", "ё"),
    ("yu", "ю"),
    ("ya", "я"),
    ("o'", "ў"),
    ("o‘", "ў"),
    ("oʻ", "ў"),
    ("g'", "ғ"),
    ("g‘", "ғ"),
    ("gʻ", "ғ"),
)

_LATIN_TO_CYR: dict[str, str] = {
    "a": "а",
    "b": "б",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "ҳ",
    "i": "и",
    "j": "ж",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "қ",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "x": "х",
    "y": "й",
    "z": "з",
    "'": "'",
}

_CYR_TO_LAT_MULTI: tuple[tuple[str, str], ...] = (
    ("ш", "sh"),
    ("ч", "ch"),
    ("нг", "ng"),
    ("ё", "yo"),
    ("ю", "yu"),
    ("я", "ya"),
    ("ў", "o'"),
    ("ғ", "g'"),
    ("қ", "q"),
    ("ҳ", "h"),
)

_CYR_TO_LAT: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ж": "j",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "x",
    "ц": "ts",
    "ъ": "'",
    "ь": "'",
    "э": "e",
    "ы": "i",
}


def _cyrillic_ratio(text: str) -> float:
    if not text:
        return 0.0
    cyr = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    return cyr / max(len(text), 1)


def latin_to_cyrillic(text: str) -> str:
    if not text:
        return text
    out: list[str] = []
    i = 0
    lower = text
    while i < len(lower):
        matched = False
        for src, dst in _LATIN_MULTI:
            chunk = lower[i : i + len(src)]
            if chunk.lower() == src:
                if chunk.isupper() and len(dst) == 1:
                    out.append(dst.upper())
                elif chunk[0].isupper() and len(dst) > 1:
                    out.append(dst[0].upper() + dst[1:])
                else:
                    out.append(dst)
                i += len(src)
                matched = True
                break
        if matched:
            continue
        ch = lower[i]
        mapped = _LATIN_TO_CYR.get(ch.lower())
        if mapped:
            out.append(mapped.upper() if ch.isupper() else mapped)
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def cyrillic_to_latin(text: str) -> str:
    if not text:
        return text
    out: list[str] = []
    i = 0
    while i < len(text):
        matched = False
        for src, dst in _CYR_TO_LAT_MULTI:
            if text.startswith(src, i):
                out.append(dst)
                i += len(src)
                matched = True
                break
        if matched:
            continue
        ch = text[i]
        mapped = _CYR_TO_LAT.get(ch.lower())
        if mapped:
            out.append(mapped.upper() if ch.isupper() else mapped)
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def ensure_uz_lat_and_cyr(
    question: str, answer: str
) -> tuple[str, str, str, str]:
    """(question_uz, answer_uz, question_cyr, answer_cyr)"""
    q = (question or "").strip()
    a = (answer or "").strip()

    if _cyrillic_ratio(q) > 0.35:
        q_cyr = q
        q_uz = cyrillic_to_latin(q)
    else:
        q_uz = q
        q_cyr = latin_to_cyrillic(q)

    if _cyrillic_ratio(a) > 0.35:
        a_cyr = a
        a_uz = cyrillic_to_latin(a)
    else:
        a_uz = a
        a_cyr = latin_to_cyrillic(a)

    return q_uz, a_uz, q_cyr, a_cyr
