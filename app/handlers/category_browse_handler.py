"""1688 kategoriyalar — ro'yxat, tanlash, mahsulot qidiruviga o'tish."""

from __future__ import annotations

from typing import Optional

from app.domain.category_present import (
    build_category_keyboard,
    empty_children_text,
    list_header,
    searching_header,
)
from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import QuestionCategory, ResponseType
from app.core.config import get_settings
from app.domain.reply_language import UZ_LAT
from app.handlers.product_search_reply import build_product_search_chat_reply
from app.services.category_resolution_service import (
    CategoryResolutionKind,
    CategoryResolutionService,
)
from app.services.product_search_service import ProductSearchService


class CategoryBrowseHandler:
    category = QuestionCategory.FAQ

    def __init__(
        self,
        resolution: Optional[CategoryResolutionService] = None,
        product_search: Optional[ProductSearchService] = None,
    ) -> None:
        self._resolution = resolution or CategoryResolutionService()
        self._product_search = product_search or ProductSearchService()

    async def reply(self, context: ChatContext) -> ChatReply:
        lang = str(context.metadata.get("reply_language") or UZ_LAT)
        text = (context.text or "").strip()
        resolved = await self._resolution.resolve_text(text, lang)
        return await self._to_reply(resolved, lang, query=text)

    async def reply_for_callback(
        self, action: str, category_id: int, back_target: int, lang: str
    ) -> ChatReply:
        if action == "b":
            resolved = await self._resolution.resolve_back(category_id, lang)
        else:
            resolved = await self._resolution.resolve_open(
                category_id, lang, back_target=back_target
            )
        return await self._to_reply(resolved, lang)

    async def try_resolve_before_product_search(
        self, context: ChatContext
    ) -> Optional[ChatReply]:
        """Noaniq katalog savollarida kategoriya yo'li; None = oddiy qidiruv."""
        lang = str(context.metadata.get("reply_language") or UZ_LAT)
        query = (
            str(context.metadata.get("product_search_query") or "").strip()
            or context.text
        )
        resolved = await self._resolution.resolve_text(query, lang)
        if resolved.kind == CategoryResolutionKind.LIST:
            return await self._to_reply(resolved, lang, query=query)
        if resolved.kind == CategoryResolutionKind.SEARCH and resolved.matched:
            return await self._to_reply(resolved, lang, query=query)
        return None

    async def _to_reply(
        self,
        resolved,
        lang: str,
        *,
        query: str = "",
    ) -> ChatReply:
        if resolved.kind == CategoryResolutionKind.SEARCH:
            keyword = resolved.search_keyword or query
            header = searching_header(lang, resolved.category_name or keyword)
            outcome = await self._product_search.search(keyword, lang)
            reply = build_product_search_chat_reply(
                outcome,
                lang,
                query=query,
                category=self.category,
                see_all_category=resolved.category_cn,
                see_all_display_name=resolved.category_name,
            )
            if reply.channel_extra is None:
                reply.channel_extra = {}
            prefix = header + "\n\n"
            reply = ChatReply(
                response_type=reply.response_type,
                text=prefix + reply.text,
                category=reply.category,
                channel_extra=reply.channel_extra,
            )
            return reply

        cats = list(resolved.categories)
        if not cats:
            return ChatReply(
                response_type=ResponseType.AUTO,
                text=empty_children_text(lang),
                category=self.category,
            )

        settings = get_settings()
        is_root = resolved.list_parent_id is None
        max_buttons = (
            settings.sahiy_category_root_max_buttons
            if is_root
            else settings.sahiy_category_child_max_buttons
        )
        keyboard = build_category_keyboard(
            cats,
            lang,
            back_target=resolved.back_target,
            current_list_parent=resolved.list_parent_id,
            max_buttons=max_buttons,
        )

        text = list_header(
            lang,
            query=resolved.query_hint if resolved.list_parent_id is None else "",
            parent_name=resolved.parent_name,
        )
        return ChatReply(
            response_type=ResponseType.AUTO,
            text=text,
            category=self.category,
            channel_extra={"inline_keyboard": keyboard, "disable_stream": True},
        )
