from functools import lru_cache

from platform_common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "auth"
    grpc_port: int = 50051
    database_name: str = "auth"

    jwt_secret: str = "dev-secret-change-me-it-must-be-at-least-32-bytes"
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60

    # Через запятую. Эти email при регистрации получают роль admin — удобно для демо.
    admin_emails: str = ""

    @property
    def admin_email_set(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.admin_emails.split(",") if e.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
