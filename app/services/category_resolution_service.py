"""Mijoz savolini kategoriya ro'yxati yoki mahsulot qidiruviga aylantirish."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from app.domain.category_match import rank_categories
from app.domain.category_present import category_display_name
from app.infrastructure.sahiy_api.categories_1688 import Category1688
from app.services.categories_1688_service import Categories1688Service

logger = logging.getLogger(__name__)


class CategoryResolutionKind(str, Enum):
    LIST = "list"
    SEARCH = "search"


@dataclass(frozen=True)
class CategoryResolution:
    kind: CategoryResolutionKind
    categories: tuple[Category1688, ...] = ()
    """Mahsulot qidiruv kaliti (kategoriya nomi / API keyword)."""
    search_keyword: str = ""
    category_name: str = ""
    list_parent_id: Optional[int] = None
    parent_name: str = ""
    query_hint: str = ""
    """True — matn bo'yicha mos kategoriya topildi; False — umumiy root ro'yxat."""
    matched: bool = True
    back_target: int = 0


class CategoryResolutionService:
    def __init__(self, categories: Optional[Categories1688Service] = None) -> None:
        self._categories = categories or Categories1688Service()

    async def resolve_text(
        self,
        text: str,
        lang: str,
    ) -> CategoryResolution:
        query = (text or "").strip()
        root = await self._categories.list_categories(parent_id=None, lang=lang)
        if not root:
            return CategoryResolution(
                kind=CategoryResolutionKind.SEARCH,
                search_keyword=query,
                query_hint=query,
            )

        ranked_root = rank_categories(root, query, lang, min_score=2.0, limit=6)
        expanded: List[Category1688] = []
        for _score, cat in ranked_root[:3]:
            expanded.append(cat)
            if cat.leaf:
                continue
            children = await self._categories.list_categories(parent_id=cat.id, lang=lang)
            for item in rank_categories(children, query, lang, min_score=2.0, limit=4):
                expanded.append(item[1])

        if not expanded:
            ranked_all = rank_categories(root, query, lang, min_score=1.5, limit=8)
            if ranked_all:
                expanded = [c for _s, c in ranked_all]

        if len(expanded) == 1:
            only = expanded[0]
            if only.leaf:
                name = category_display_name(only, lang)
                return CategoryResolution(
                    kind=CategoryResolutionKind.SEARCH,
                    search_keyword=name or only.name_en or only.name_uz,
                    category_name=name,
                    query_hint=query,
                )
            children = await self._categories.list_categories(parent_id=only.id, lang=lang)
            if not children:
                name = category_display_name(only, lang)
                return CategoryResolution(
                    kind=CategoryResolutionKind.SEARCH,
                    search_keyword=name or only.name_en or only.name_uz,
                    category_name=name,
                    query_hint=query,
                )
            child_ranked = rank_categories(children, query, lang, min_score=1.5, limit=8)
            if len(child_ranked) == 1:
                child = child_ranked[0][1]
                if child.leaf:
                    name = category_display_name(child, lang)
                    return CategoryResolution(
                        kind=CategoryResolutionKind.SEARCH,
                        search_keyword=name or child.name_en or child.name_uz,
                        category_name=name,
                        query_hint=query,
                    )
            return CategoryResolution(
                kind=CategoryResolutionKind.LIST,
                categories=tuple(children),
                list_parent_id=only.id,
                parent_name=category_display_name(only, lang),
                query_hint=query,
            )

        if expanded:
            return CategoryResolution(
                kind=CategoryResolutionKind.LIST,
                categories=tuple(expanded[:8]),
                list_parent_id=None,
                query_hint=query,
            )

        return CategoryResolution(
            kind=CategoryResolutionKind.LIST,
            categories=tuple(root[:12]),
            list_parent_id=None,
            query_hint=query,
            matched=False,
        )

    async def resolve_open(
        self,
        category_id: int,
        lang: str,
        *,
        back_target: int = 0,
    ) -> CategoryResolution:
        from app.infrastructure.sahiy_api.categories_1688 import find_category_in_cache

        cat = find_category_in_cache(category_id)
        children = await self._categories.list_categories(parent_id=category_id, lang=lang)
        if children:
            name = category_display_name(cat, lang) if cat else ""
            return CategoryResolution(
                kind=CategoryResolutionKind.LIST,
                categories=tuple(children[:12]),
                list_parent_id=category_id,
                parent_name=name,
                back_target=back_target,
            )

        name = category_display_name(cat, lang) if cat else ""
        keyword = name or (cat.name_en if cat else "") or (cat.name_uz if cat else "")
        if not keyword:
            logger.warning("category %s has no name for search", category_id)
            keyword = str(category_id)
        return CategoryResolution(
            kind=CategoryResolutionKind.SEARCH,
            search_keyword=keyword,
            category_name=name or keyword,
        )

    async def resolve_back(
        self,
        list_parent_id: int,
        lang: str,
    ) -> CategoryResolution:
        if list_parent_id <= 0:
            root = await self._categories.list_categories(parent_id=None, lang=lang)
            return CategoryResolution(
                kind=CategoryResolutionKind.LIST,
                categories=tuple(root[:12]),
                list_parent_id=None,
            )
        items = await self._categories.list_categories(parent_id=list_parent_id, lang=lang)
        from app.infrastructure.sahiy_api.categories_1688 import find_category_in_cache

        parent = find_category_in_cache(list_parent_id)
        parent_name = category_display_name(parent, lang) if parent else ""
        return CategoryResolution(
            kind=CategoryResolutionKind.LIST,
            categories=tuple(items[:12]),
            list_parent_id=list_parent_id,
            parent_name=parent_name,
        )
