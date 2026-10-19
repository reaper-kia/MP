from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # адреса gRPC-сервисов (в Docker: SEARCH_GRPC_TARGET=search_service:50053)
    search_grpc_target: str = "localhost:50053"
    collector_grpc_target: str = "localhost:50054"
    ml_grpc_target: str = "localhost:50055"

    # таймауты вызовов, секунды
    grpc_timeout_seconds: float = 5.0
    resolve_timeout_seconds: float = 25.0  # search → collector.ResolveSource (20) + запас
    analyze_timeout_seconds: float = 25.0
    import_timeout_seconds: float = 180.0
    export_timeout_seconds: float = 60.0

    # через запятую; для фронта на vite dev-сервере. Расширение Chrome — по cors_origin_regex
    cors_origins: str = "http://localhost:5173"
    cors_origin_regex: str = r"chrome-extension://.*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
