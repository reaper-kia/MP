from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    grpc_address: str = "[::]:50053"

    database_url: str = "postgresql+asyncpg://search:search_local@localhost:5435/search"
    database_echo: bool = False

    # соседи (межсервисный gRPC)
    collector_grpc_target: str = "localhost:50054"
    ml_grpc_target: str = "localhost:50055"

    # таймауты вызовов, секунды
    collector_resolve_timeout: float = 20.0
    collector_collect_timeout: float = 60.0
    ml_analyze_timeout: float = 20.0
    ml_score_timeout: float = 60.0
    ml_group_timeout: float = 60.0

    # пайплайн (B2-04)
    collect_concurrency: int = 5
    score_batch_size: int = 30
    score_concurrency: int = 3
    max_posts_per_source: int = 300
    max_posts_per_platform_search: int = 500
    region_terms: list[str] = ["Красноярск", "Красноярский край"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
