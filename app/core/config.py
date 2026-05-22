from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "sahiy-agent"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"
    log_json: bool = False
    host: str = "0.0.0.0"
    port: int = 8001

    database_url: str = "postgresql+asyncpg://sahiy:sahiy_test@localhost:5433/sahiy_agent"

    # AI provider: auto | openai | anthropic | rules
    # auto = Anthropic → OpenAI → rules (per request, on API/quota errors)
    # Optional override: AI_PROVIDER_CHAIN=anthropic,openai
    ai_provider: str = "auto"
    ai_provider_chain: str = ""
    ai_max_concurrent: int = 10
    ai_timeout_seconds: int = 30

    # OpenAI (GPT)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # Anthropic (Claude)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

    # Embeddings: auto | openai | mock (Claude has no embedding API — openai → mock)
    embedding_provider: str = "auto"

    rag_similarity_threshold: float = 0.85
    rag_top_k: int = 7
    rag_max_tokens: int = 1024
    ai_order_max_tokens: int = 1024
    embedding_dimension: int = 1536

    telegram_bot_token: str = ""
    telegram_http_timeout_seconds: int = 60
    telegram_send_retries: int = 3
    telegram_typing_interval_seconds: float = 4.0

    # Close active session after this many hours without messages (0 = disabled)
    session_idle_hours: float = 24.0

    go_backend_url: str = "http://localhost:8080"
    go_backend_timeout_seconds: int = 10

    # Sahiy Laravel API (service_user — buyurtma holati)
    sahiy_api_base_url: str = ""
    sahiy_api_timeout_seconds: int = 15
    service_user_phone: str = ""
    service_user_password: str = ""
    service_user_device_id: str = "sahiy-agent"
    service_user_token_buffer_seconds: int = 60
    sahiy_daigou_page_size: int = 10
    sahiy_daigou_max_pages_search: int = 5
    pickup_points_cache_ttl_seconds: int = 3600

    @property
    def has_service_user(self) -> bool:
        return bool(
            self.sahiy_api_base_url.strip()
            and self.service_user_phone.strip()
            and self.service_user_password
        )

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key.strip())

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key.strip())

    def ai_chain_providers(self) -> List[str]:
        """Chat LLM try order (excludes rules; added at runtime on failure)."""
        if self.ai_provider_chain.strip():
            return [
                name.strip().lower()
                for name in self.ai_provider_chain.split(",")
                if name.strip()
            ]

        choice = self.ai_provider.strip().lower()
        if choice == "rules":
            return []
        if choice == "auto":
            chain: List[str] = []
            if self.has_anthropic:
                chain.append("anthropic")
            if self.has_openai:
                chain.append("openai")
            return chain
        if choice == "anthropic":
            chain = ["anthropic"]
            if self.has_openai:
                chain.append("openai")
            return chain
        if choice == "openai":
            chain = ["openai"]
            if self.has_anthropic:
                chain.append("anthropic")
            return chain
        return [choice]

    def resolved_ai_provider(self) -> str:
        """Primary provider label for logs (chain summarized when multiple)."""
        chain = self.ai_chain_providers()
        if not chain:
            return "rules"
        if len(chain) == 1:
            return chain[0]
        return f"chain({','.join(chain)}→rules)"

    def embedding_chain_providers(self) -> List[str]:
        """Embedding try order; mock is always the last fallback."""
        choice = self.embedding_provider.strip().lower()
        if choice == "auto":
            if self.has_openai:
                return ["openai", "mock"]
            return ["mock"]
        if choice == "openai":
            return ["openai", "mock"]
        if choice == "mock":
            return ["mock"]
        return [choice]

    def resolved_embedding_provider(self) -> str:
        chain = self.embedding_chain_providers()
        if len(chain) == 1:
            return chain[0]
        return f"chain({','.join(chain)})"


@lru_cache
def get_settings() -> Settings:
    return Settings()
