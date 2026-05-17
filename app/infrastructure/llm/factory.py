from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.infrastructure.llm.chained_client import ChainedAiClient
from app.infrastructure.llm.claude_client import ClaudeClient
from app.infrastructure.llm.gpt_client import GptClient
from app.infrastructure.llm.ports import AiClient
from app.infrastructure.llm.rules_ai import RulesAi


def _client_for_name(name: str, settings: Settings) -> Optional[AiClient]:
    if name == "openai":
        if settings.has_openai:
            return GptClient(settings)
        return None
    if name == "anthropic":
        if settings.has_anthropic:
            return ClaudeClient(settings)
        return None
    if name == "rules":
        return RulesAi()
    return None


def _build_chain(providers: List[AiClient]) -> AiClient:
    if not providers:
        return RulesAi()
    return ChainedAiClient(providers)


def _require_primary_key(settings: Settings, chain_names: List[str]) -> None:
    choice = settings.ai_provider.strip().lower()
    if choice == "openai" and not settings.has_openai:
        raise ConfigurationError("AI_PROVIDER=openai but OPENAI_API_KEY is empty")
    if choice == "anthropic" and not settings.has_anthropic:
        raise ConfigurationError("AI_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty")


@lru_cache
def create_ai_client() -> AiClient:
    settings = get_settings()
    choice = settings.ai_provider.strip().lower()

    if choice == "rules":
        return RulesAi()

    chain_names = settings.ai_chain_providers()
    _require_primary_key(settings, chain_names)

    chain: List[AiClient] = []
    for name in chain_names:
        if name == "rules":
            continue
        client = _client_for_name(name, settings)
        if client is not None:
            chain.append(client)

    if not chain:
        return RulesAi()

    return _build_chain(chain)
