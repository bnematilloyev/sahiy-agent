"""LLM routing labels — which backend path handles the turn."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ConversationRoute(str, Enum):
    FAQ = "faq"
    API = "api"
    TICKET = "ticket"
    PICKUP = "pickup"
    PRODUCT_SEARCH = "product_search"
    CATEGORY = "category"
    CHITCHAT = "chitchat"


@dataclass(frozen=True)
class RouteDecision:
    route: ConversationRoute
    """1688 qidiruv uchun ajratilgan qisqa so'rov (bo'sh bo'lsa — mijoz matni)."""
    search_query: Optional[str] = None
    """Mijoz javob tili: uz_lat | uz_cyrl | ru | en | zh."""
    reply_language: Optional[str] = None
