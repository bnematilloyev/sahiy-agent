from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.infrastructure.embeddings.factory import create_embedder
from app.infrastructure.embeddings.fallback_embedder import FallbackEmbedder
from app.infrastructure.llm.chained_client import ChainedAiClient
from app.infrastructure.llm.claude_client import ClaudeClient
from app.infrastructure.llm.factory import create_ai_client
from app.infrastructure.llm.gpt_client import GptClient
from app.infrastructure.llm.rules_ai import RulesAi


def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_ai_chain_auto_prefers_anthropic_then_openai():
    settings = _settings(
        ai_provider="auto",
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-test",
    )
    assert settings.ai_chain_providers() == ["anthropic", "openai"]
    assert settings.resolved_ai_provider() == "chain(anthropic,openai→rules)"


def test_ai_chain_anthropic_includes_openai_fallback():
    settings = _settings(
        ai_provider="anthropic",
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-test",
    )
    assert settings.ai_chain_providers() == ["anthropic", "openai"]


def test_ai_chain_auto_anthropic_only():
    settings = _settings(ai_provider="auto", anthropic_api_key="sk-ant-test")
    assert settings.ai_chain_providers() == ["anthropic"]
    assert settings.resolved_ai_provider() == "anthropic"


def test_ai_chain_custom_env_override():
    settings = _settings(
        ai_provider="auto",
        ai_provider_chain="openai,anthropic",
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-test",
    )
    assert settings.ai_chain_providers() == ["openai", "anthropic"]


def test_resolved_provider_rules_when_no_keys():
    settings = _settings(ai_provider="auto")
    assert settings.ai_chain_providers() == []
    assert settings.resolved_ai_provider() == "rules"


def test_embedding_chain_auto():
    settings = _settings(embedding_provider="auto", openai_api_key="sk-test")
    assert settings.embedding_chain_providers() == ["openai", "mock"]
    assert settings.resolved_embedding_provider() == "chain(openai,mock)"


@patch("app.infrastructure.llm.factory.get_settings")
def test_create_ai_client_rules(mock_get_settings):
    mock_get_settings.return_value = _settings(ai_provider="rules")
    create_ai_client.cache_clear()
    assert isinstance(create_ai_client(), RulesAi)
    create_ai_client.cache_clear()


@patch("app.infrastructure.embeddings.factory.get_settings")
def test_create_embedder_openai_with_mock_fallback(mock_get_settings):
    mock_get_settings.return_value = _settings(
        embedding_provider="openai",
        openai_api_key="sk-test",
    )
    create_embedder.cache_clear()
    embedder = create_embedder()
    assert isinstance(embedder, FallbackEmbedder)
    create_embedder.cache_clear()


@patch("app.infrastructure.llm.factory.get_settings")
def test_create_ai_client_chains_anthropic_and_openai(mock_get_settings):
    mock_get_settings.return_value = _settings(
        ai_provider="anthropic",
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-test",
    )
    create_ai_client.cache_clear()
    client = create_ai_client()
    assert isinstance(client, ChainedAiClient)
    assert len(client._providers) == 2
    assert isinstance(client._providers[0], ClaudeClient)
    assert isinstance(client._providers[1], GptClient)
    create_ai_client.cache_clear()
