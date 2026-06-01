from __future__ import annotations

import pytest

from app.domain.conversation_route import ConversationRoute
from app.services.conversation_router import _parse_router_json


def test_parse_router_json_category():
    raw = '{"route":"category","search_query":""}'
    decision = _parse_router_json(raw)
    assert decision is not None
    assert decision.route.value == "category"


def test_parse_router_json_product_search():
    raw = '{"route":"product_search","search_query":"inglizcha kitob"}'
    decision = _parse_router_json(raw)
    assert decision is not None
    assert decision.route == ConversationRoute.PRODUCT_SEARCH
    assert decision.search_query == "inglizcha kitob"


def test_parse_router_json_reply_language():
    raw = '{"route":"product_search","search_query":"kurta","reply_language":"ru"}'
    decision = _parse_router_json(raw)
    assert decision is not None
    assert decision.reply_language == "ru"


def test_parse_router_json_single_token():
    assert _parse_router_json("product_search").route == ConversationRoute.PRODUCT_SEARCH


def test_fallback_other_product_types():
    from app.domain.product_search_intent import is_product_search_intent

    assert is_product_search_intent("boshqa tovar turi bormi")
