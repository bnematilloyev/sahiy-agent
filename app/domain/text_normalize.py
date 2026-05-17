"""Shared text normalization for keyword/scope matching."""


def normalize_text(text: str) -> str:
    return text.lower().replace("ʻ", "'").replace("'", "'").replace("’", "'")
