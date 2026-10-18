from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    grpc_address: str = "[::]:50051"

    database_url: str = "postgresql+asyncpg://auth:auth_local@localhost:5433/auth"
    database_echo: bool = False

    jwt_secret: str = "dev-secret-change-me-it-must-be-at-least-32-bytes"
    jwt_issuer: str = "mp-auth"
    jwt_audience: str = "mp"
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60

    # через запятую: эти email при регистрации получают роль admin
    admin_emails: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def admin_email_set(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.admin_emails.split(",") if e.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
