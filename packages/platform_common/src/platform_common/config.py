"""Базовые настройки сервиса. Значения по умолчанию рассчитаны на локальный запуск
(`make infra` + `make run s=<service>`), в Docker их переопределяет compose.yaml."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class BaseServiceSettings(BaseSettings):
    service_name: str = "service"
    log_level: str = "INFO"

    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051

    # Один Postgres на всё, у каждого сервиса своя БД (создаётся автоматически при старте).
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "app"
    postgres_password: str = "app"
    database_name: str = "app"
    database_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    kafka_enabled: bool = False
    kafka_bootstrap_servers: str = "localhost:9094"

    # Таймаут исходящих gRPC-вызовов (сервис → сервис), секунды.
    grpc_client_timeout: float = 5.0

    model_config = SettingsConfigDict(
        # корневой .env (общие секреты), затем .env в папке сервиса — если есть
        env_file=(REPO_ROOT_ENV, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def grpc_address(self) -> str:
        return f"{self.grpc_host}:{self.grpc_port}"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.database_name}"
        )
