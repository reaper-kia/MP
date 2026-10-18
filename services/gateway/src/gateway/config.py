from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # тот же секрет, что у auth_service: им проверяем access-токены
    jwt_secret: str = "dev-secret-change-me-it-must-be-at-least-32-bytes"
    jwt_issuer: str = "mp-auth"
    jwt_audience: str = "mp"

    # адреса gRPC-сервисов (в Docker: AUTH_GRPC_TARGET=auth_service:50051)
    auth_grpc_target: str = "localhost:50051"
    example_grpc_target: str = "localhost:50052"
    grpc_timeout_seconds: float = 5.0

    # через запятую; для фронта на vite dev-сервере
    cors_origins: str = "http://localhost:5173"
    # true только за HTTPS, иначе браузер не сохранит refresh-cookie
    cookie_secure: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
