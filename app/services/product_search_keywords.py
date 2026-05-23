"""Mahsulot qidiruv: mijoz matnidan 1688 uchun xitoycha keyword ajratish."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.core.prompts import wrap_user_message
from app.infrastructure.llm.factory import create_ai_client
from app.infrastructure.llm.ports import AiClient

logger = logging.getLogger(__name__)

_PRODUCT_SEARCH_KEYWORD_SYSTEM = """Sen Sahiy do'koni mahsulot qidiruv yordamchisisan.
Mijoz xabaridan 1688/Taobao qidiruvi uchun kalit so'zlarni ajrat.

CHIQISH: faqat bitta JSON qator, boshqa matn yo'q:
{"keyword_zh":"...","display_short":"..."}

QOIDALAR:
- keyword_zh: soddalashtirilgan xitoycha (简体中文), bo'shliq bilan, maksimal 6–8 so'z.
  Faqat mahsulot turi, rang, mavsum, material, uslub — "menga", "ko'rsat", "eng yaxshi", "arzon" kabi so'zlarni QO'SHMA.
- display_short: mijoz tilida qisqa tavsif (maksimal 6 so'z), qidiruv sarlavhasi uchun.
- Agar mijoz allaqachon qisqa mahsulot nomi yozsa (1–3 so'z), keyword_zh ga mos xitoycha tarjima qil.

MISOLLAR:
- "menga sariq kepka kerak" → {"keyword_zh":"黄色 帽子","display_short":"sariq kepka"}
- "yozgi kolleksiya arzon kiyim" → {"keyword_zh":"夏季 女装 便宜","display_short":"yozgi arzon kiyim"}
- "telefon" → {"keyword_zh":"手机","display_short":"telefon"}
"""

# Fallback: tez-tez uchraydigan so'zlar (lotin → xitoycha)
_UZ_TO_ZH: dict[str, str] = {
    "kepka": "帽子",
    "kiyim": "服装",
    "kiyimlar": "服装",
    "ko'ylak": "连衣裙",
    "shim": "裤子",
    "qish": "冬季",
    "yoz": "夏季",
    "yozgi": "夏季",
    "qishki": "冬季",
    "sariq": "黄色",
    "qizil": "红色",
    "qora": "黑色",
    "oq": "白色",
    "ko'k": "蓝色",
    "yashil": "绿色",
    "telefon": "手机",
    "sumka": "包",
    "poyabzal": "鞋",
    "tufli": "鞋",
    "soat": "手表",
    "kolleksiya": "新款",
    "arzon": "便宜",
    "sport": "运动",
    "lego": "乐高",
    "kitob": "书",
    "inglizcha": "英文",
    "ingliz": "英文",
    "oyinchoq": "玩具",
    "o'yinchoq": "玩具",
    "oyinchog": "玩具",
    "oyinchogi": "玩具",
    "inglizcha kitob": "英文 书",
    "ruscha": "俄文",
    "kitoblar": "书籍",
}

_STOPWORDS = frozenset(
    {
        "menga",
        "men",
        "siz",
        "kerak",
        "ko'rsat",
        "korsat",
        "ber",
        "bering",
        "iltimos",
        "eng",
        "yaxshi",
        "sifatli",
        "arzon",
        "arzonini",
        "qaysi",
        "qanday",
        "bormi",
        "bor",
        "mahsulot",
        "mahsulotlar",
        "mahsulotlarining",
        "tovar",
        "tovarlarni",
        "qidirish",
        "topib",
        "oling",
        "and",
        "the",
        "for",
        "show",
        "me",
        "please",
        "want",
        "need",
    }
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True)
class ProductSearchKeywords:
    keyword_zh: str
    display_short: str


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _fallback_keywords(query: str) -> ProductSearchKeywords:
    raw = query.strip()
    if _has_cjk(raw):
        short = raw[:40].strip()
        return ProductSearchKeywords(keyword_zh=short, display_short=short)

    tokens = re.findall(r"[\w']+", raw.lower())
    zh_parts: list[str] = []
    display_parts: list[str] = []
    for tok in tokens:
        if tok in _STOPWORDS or len(tok) < 2:
            continue
        display_parts.append(tok)
        zh_parts.append(_UZ_TO_ZH.get(tok, tok))

    keyword_zh = " ".join(zh_parts)[:60].strip() or raw[:40]
    display_short = " ".join(display_parts[:6]) or raw[:40]
    return ProductSearchKeywords(keyword_zh=keyword_zh, display_short=display_short[:80])


def _parse_llm_json(text: str) -> ProductSearchKeywords | None:
    body = text.strip()
    if "```" in body:
        match = re.search(r"\{[^{}]*\}", body, re.DOTALL)
        if match:
            body = match.group(0)
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    keyword_zh = str(data.get("keyword_zh") or "").strip()
    display_short = str(data.get("display_short") or "").strip()
    if not keyword_zh or not _has_cjk(keyword_zh):
        return None
    if not display_short:
        display_short = keyword_zh
    return ProductSearchKeywords(
        keyword_zh=keyword_zh[:80],
        display_short=display_short[:80],
    )


async def extract_product_search_keywords(
    query: str,
    *,
    reply_language: str = "uz_lat",
    ai: AiClient | None = None,
) -> ProductSearchKeywords:
    """Mijoz matnidan API keyword (xitoycha) va qisqa sarlavha."""
    cleaned = (query or "").strip()
    if not cleaned:
        return ProductSearchKeywords(keyword_zh="", display_short="")

    if _has_cjk(cleaned) and len(cleaned) <= 40:
        return ProductSearchKeywords(keyword_zh=cleaned, display_short=cleaned)

    client = ai if ai is not None else create_ai_client()
    if not client.is_available:
        return _fallback_keywords(cleaned)

    user_prompt = (
        f"Mijoz tili: {reply_language}\n"
        f"Mijoz xabari:\n{wrap_user_message(cleaned, max_len=500)}"
    )
    try:
        raw = await client.complete(
            _PRODUCT_SEARCH_KEYWORD_SYSTEM,
            user_prompt,
            max_tokens=120,
        )
        parsed = _parse_llm_json(raw)
        if parsed:
            logger.info(
                "product keyword extracted: %r -> zh=%r display=%r",
                cleaned[:60],
                parsed.keyword_zh,
                parsed.display_short,
            )
            return parsed
    except Exception as exc:
        logger.warning("product keyword LLM failed: %s", exc)

    return _fallback_keywords(cleaned)
