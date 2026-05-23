"""Mahsulot qidiruv — 1688 API orqali tavsiyalar."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional

from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import QuestionCategory, ResponseType
from app.domain.reply_language import UZ_LAT
from app.domain.telegram_menu import (
    PRODUCT_SEARCH_EMPTY,
    PRODUCT_SEARCH_ERROR,
    PRODUCT_SEARCH_HEADER,
    PRODUCT_SEARCH_TOO_SHORT,
    localize_menu,
)
from app.services.product_search_service import ProductSearchService, ProductSearchStatus


class ProductSearchHandler:
    category = QuestionCategory.FAQ

    def __init__(self, service: Optional[ProductSearchService] = None) -> None:
        self._service = service or ProductSearchService()

    async def reply(self, context: ChatContext) -> ChatReply:
        lang = str(context.metadata.get("reply_language") or UZ_LAT)
        query = (
            str(context.metadata.get("product_search_query") or "").strip()
            or context.text
        )
        outcome = await self._service.search(query, lang)

        if outcome.status == ProductSearchStatus.TOO_SHORT:
            return ChatReply(
                response_type=ResponseType.AUTO,
                text=localize_menu(PRODUCT_SEARCH_TOO_SHORT, lang),
                category=self.category,
            )
        if outcome.status in (
            ProductSearchStatus.NOT_CONFIGURED,
            ProductSearchStatus.ERROR,
        ):
            return ChatReply(
                response_type=ResponseType.AUTO,
                text=localize_menu(PRODUCT_SEARCH_ERROR, lang),
                category=self.category,
            )
        if outcome.status == ProductSearchStatus.EMPTY:
            return ChatReply(
                response_type=ResponseType.AUTO,
                text=localize_menu(PRODUCT_SEARCH_EMPTY, lang),
                category=self.category,
            )

        header = localize_menu(
            PRODUCT_SEARCH_HEADER,
            lang,
            keyword=outcome.display_keyword,
            count=str(len(outcome.items)),
        )
        extra: Dict[str, Any] = {
            "product_search_items": [asdict(item) for item in outcome.items],
            "product_search_cny_to_uzs": outcome.cny_to_uzs,
            "disable_stream": True,
        }
        return ChatReply(
            response_type=ResponseType.AUTO,
            text=header,
            category=self.category,
            channel_extra=extra,
        )
