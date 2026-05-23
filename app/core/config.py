from functools import lru_cache
from typing import Any, List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _strip_inline_env_comment(value: Any) -> Any:
    """`.env` da `KEY=value  # izoh` — izohni qiymatdan ajratish."""
    if not isinstance(value, str):
        return value
    idx = value.find(" #")
    if idx != -1:
        return value[:idx].strip()
    return value.strip()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def _strip_dotenv_inline_comments(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {key: _strip_inline_env_comment(val) for key, val in data.items()}
        return data

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
    telegram_stream_enabled: bool = True
    # Bir editda taxminan necha belgi qo'shiladi (base; adaptive scales up under load)
    telegram_stream_edit_min_chars: int = 8
    # Pump tick (yangilanish chastotasi)
    telegram_stream_edit_delay_seconds: float = 0.05
    # Ikki edit orasidagi minimal interval (Telegram rate-limit) — 0.15 ≈ 6 edit/s
    telegram_stream_min_edit_gap_seconds: float = 0.15
    telegram_stream_show_cursor: bool = True
    # Xizmat bahosi: oxirgi bot javobidan keyin mijoz jim turganda (sekund)
    telegram_rating_inactivity_seconds: float = 1800.0

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

    # Sahiy admin API (panel login — SKU + rasm olish uchun)
    sahiy_admin_username: str = ""
    sahiy_admin_password: str = ""
    sahiy_admin_access_token: str = ""  # Panel JWT — captcha kerak emas (qo'lda .env ga)
    sahiy_admin_token_ttl_seconds: int = 3000   # 50 min (expires_in=3600)
    sahiy_admin_captcha_max_attempts: int = 5    # panel login: yangi captcha urinishlari
    sahiy_admin_captcha_model: str = ""           # bo'sh = ANTHROPIC_MODEL ishlatiladi
    sahiy_sku_photos_enabled: bool = True        # False = rasmsiz, tez rejim

    # CNY → UZS (SKU narxlarini so'mda ko'rsatish)
    sahiy_exchange_api_url: str = "https://api.abusahiy.uz/api/client/exchange/rates"
    sahiy_exchange_client_uuid: str = "259bb5ce-16a8-4d4a-81d5-1aaba0ba4a54"
    sahiy_exchange_cache_ttl_seconds: int = 3600
    sahiy_exchange_cny_uzs_fallback: float = 1750.0

    # Mahsulot qidiruv (client API) va Sahiy ilova deeplink
    sahiy_product_search_page_size: int = 4
    sahiy_product_search_see_all_page_size: int = 20
    sahiy_product_search_sort: str = "asc"
    sahiy_goods_deeplink_base: str = "https://sahiy.uz/GoodsDetailView?u="
    sahiy_product_search_deeplink_base: str = "https://sahiy.uz/PurchaseSearchView"
    sahiy_category_search_deeplink_base: str = "https://sahiy.uz/search"
    sahiy_1688_categories_cache_ttl_seconds: int = 86400
    sahiy_category_root_max_buttons: int = 64
    sahiy_category_child_max_buttons: int = 12

    # custom-daigou-orders (service_user — SKU + express_num qidiruv)
    sahiy_custom_daigou_timeout_seconds: int = 45
    sahiy_custom_daigou_max_pages: int = 5

    @property
    def sahiy_admin_captcha_model_resolved(self) -> str:
        return self.sahiy_admin_captcha_model.strip() or self.anthropic_model

    @property
    def has_admin_api(self) -> bool:
        return bool(
            self.sahiy_admin_access_token.strip()
            or (
                self.sahiy_admin_username.strip()
                and self.sahiy_admin_password.strip()
            )
        )

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
