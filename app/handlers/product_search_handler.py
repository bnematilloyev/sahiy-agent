"""Mahsulot qidiruv — 1688 API orqali tavsiyalar."""

from __future__ import annotations

from typing import Optional

from app.domain.category_intent import should_resolve_via_categories
from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import QuestionCategory
from app.domain.reply_language import UZ_LAT
from app.handlers.category_browse_handler import CategoryBrowseHandler
from app.handlers.product_search_reply import build_product_search_chat_reply
from app.services.product_search_service import ProductSearchService


class ProductSearchHandler:
    category = QuestionCategory.FAQ

    def __init__(
        self,
        service: Optional[ProductSearchService] = None,
        category_browse: Optional[CategoryBrowseHandler] = None,
    ) -> None:
        self._service = service or ProductSearchService()
        self._category = category_browse

    async def reply(self, context: ChatContext) -> ChatReply:
        lang = str(context.metadata.get("reply_language") or UZ_LAT)
        query = (
            str(context.metadata.get("product_search_query") or "").strip()
            or context.text
        )
        if self._category is not None and should_resolve_via_categories(query):
            cat_reply = await self._category.try_resolve_before_product_search(context)
            if cat_reply is not None:
                return cat_reply

        outcome = await self._service.search(query, lang)
        return build_product_search_chat_reply(
            outcome, lang, query=query, category=self.category
        )
