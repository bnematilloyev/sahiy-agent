"""Mahsulot qidiruv natijasidan ChatReply yig'ish (handlerlar uchun umumiy)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional

from app.domain.dto import ChatReply
from app.domain.enums import QuestionCategory, ResponseType
from app.domain.reply_language import UZ_LAT
from app.domain.telegram_menu import (
    PRODUCT_SEARCH_EMPTY,
    PRODUCT_SEARCH_ERROR,
    PRODUCT_SEARCH_HEADER,
    PRODUCT_SEARCH_TOO_SHORT,
    localize_menu,
)
from app.services.product_search_service import ProductSearchOutcome, ProductSearchStatus


def build_product_search_chat_reply(
    outcome: ProductSearchOutcome,
    lang: str,
    *,
    query: str = "",
    category: QuestionCategory = QuestionCategory.FAQ,
) -> ChatReply:
    if outcome.status == ProductSearchStatus.TOO_SHORT:
        return ChatReply(
            response_type=ResponseType.AUTO,
            text=localize_menu(PRODUCT_SEARCH_TOO_SHORT, lang),
            category=category,
        )
    if outcome.status in (ProductSearchStatus.NOT_CONFIGURED, ProductSearchStatus.ERROR):
        return ChatReply(
            response_type=ResponseType.AUTO,
            text=localize_menu(PRODUCT_SEARCH_ERROR, lang),
            category=category,
        )
    if outcome.status == ProductSearchStatus.EMPTY:
        return ChatReply(
            response_type=ResponseType.AUTO,
            text=localize_menu(PRODUCT_SEARCH_EMPTY, lang),
            category=category,
        )

    header = localize_menu(
        PRODUCT_SEARCH_HEADER,
        lang,
        keyword=outcome.display_keyword,
        count=str(len(outcome.items)),
    )
    see_all_keyword = outcome.api_keyword or outcome.display_keyword or query
    extra: Dict[str, Any] = {
        "product_search_items": [asdict(item) for item in outcome.items],
        "product_search_cny_to_uzs": outcome.cny_to_uzs,
        "product_search_see_all_keyword": see_all_keyword,
        "disable_stream": True,
    }
    return ChatReply(
        response_type=ResponseType.AUTO,
        text=header,
        category=category,
        channel_extra=extra,
    )
