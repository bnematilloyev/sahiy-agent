"""Shared text normalization: apostrophe + Cyrillic (Uzbek/Russian) → Latin."""

from __future__ import annotations

# Uzun juftlar avval (тс, ш, ғ …)
_CYRILLIC_MULTI: tuple[tuple[str, str], ...] = (
    ("щ", "sh"),
    ("ш", "sh"),
    ("ч", "ch"),
    ("ц", "ts"),
    ("ё", "yo"),
    ("ю", "yu"),
    ("я", "ya"),
    ("ғ", "g'"),
    ("ў", "o'"),
    ("қ", "q"),
    ("ҳ", "h"),
    ("ж", "j"),
    ("ъ", "'"),
    ("ь", "'"),
    ("э", "e"),
    ("ы", "y"),
)

_CYRILLIC_SINGLE: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
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
    "ў": "o'",
    "ғ": "g'",
    "қ": "q",
    "ҳ": "h",
}


def _has_cyrillic(text: str) -> bool:
    return any("\u0400" <= ch <= "\u04ff" for ch in text)


def transliterate_cyrillic_to_latin(text: str) -> str:
    """O'zbek va rus kirill → lotin (kalit so'z moslash uchun)."""
    if not text:
        return text
    lower = text.lower()
    out: list[str] = []
    i = 0
    n = len(lower)
    while i < n:
        matched = False
        for src, dst in _CYRILLIC_MULTI:
            if lower.startswith(src, i):
                out.append(dst)
                i += len(src)
                matched = True
                break
        if matched:
            continue
        ch = lower[i]
        out.append(_CYRILLIC_SINGLE.get(ch, ch))
        i += 1
    return "".join(out)


def normalize_text(text: str) -> str:
    """Barcha keyword/scope tekshiruvlari shu funksiyadan o'tadi."""
    t = (text or "").strip().lower()
    t = t.replace("ʻ", "'").replace("'", "'").replace("'", "'")
    if _has_cyrillic(t):
        t = transliterate_cyrillic_to_latin(t)
    return t
