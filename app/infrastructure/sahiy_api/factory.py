"""Shared Sahiy API stack (token cache survives across requests)."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional, Tuple

from app.core.config import Settings, get_settings
from app.infrastructure.sahiy_api.auth import ServiceUserAuth
from app.infrastructure.sahiy_api.client import SahiyApiClient
from app.infrastructure.sahiy_api.customer import CustomerApi
from app.infrastructure.sahiy_api.categories_1688 import clear_categories_1688_cache
from app.infrastructure.sahiy_api.pickup_points import clear_pickup_points_cache


@lru_cache
def get_sahiy_customer_api() -> Optional[CustomerApi]:
    settings = get_settings()
    if not settings.has_service_user:
        return None
    auth = ServiceUserAuth(settings)
    client = SahiyApiClient(auth)
    return CustomerApi(client)


@lru_cache
def get_sahiy_api_client() -> Optional[SahiyApiClient]:
    settings = get_settings()
    if not settings.has_service_user:
        return None
    return SahiyApiClient(ServiceUserAuth(settings))


def clear_sahiy_api_cache() -> None:
    get_sahiy_customer_api.cache_clear()
    get_sahiy_api_client.cache_clear()
    clear_pickup_points_cache()
    clear_categories_1688_cache()
