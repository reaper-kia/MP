from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from platform_common.config import REPO_ROOT_ENV


class Settings(BaseSettings):
    service_name: str = "gateway"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    jwt_secret: str = "dev-secret-change-me-it-must-be-at-least-32-bytes"

    # Адреса gRPC-сервисов. В Docker переопределяются через <NAME>_GRPC_TARGET.
    auth_grpc_target: str = "localhost:50051"
    example_grpc_target: str = "localhost:50052"
    # >>> grpc targets (new_service.py вставляет строки выше)
    grpc_timeout: float = 5.0

    redis_url: str = "redis://localhost:6379/0"

    # Через запятую. Для прода за nginx фронта (тот же origin) CORS не нужен вовсе.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    refresh_cookie_path: str = "/api/v1/auth"
    cookie_secure: bool = False

    login_rate_limit: int = 10
    login_rate_window_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT_ENV, ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
