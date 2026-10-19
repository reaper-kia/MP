from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    grpc_address: str = "[::]:50054"

    # true — все площадки отдают тестовые посты [FAKE]. На демо — ВСЕГДА false.
    collector_fake: bool = False

    # VK API (B1-03)
    vk_service_token: str = ""
    vk_api_version: str = "5.199"
    vk_requests_per_second: float = 3.0

    # Yandex Search API — глобальный поиск по OK / MAX / сайтам (B1-06)
    yc_folder_id: str = ""
    yc_search_api_key: str = ""

    # HTTP к площадкам
    http_timeout_seconds: float = 15.0
    http_user_agent: str = "Mozilla/5.0 (X11; Linux x86_64) MP-mediamonitoring/0.1"

    # Лимиты по умолчанию, если в запросе max_posts = 0
    default_max_posts_source: int = 300
    default_max_posts_search: int = 500

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
