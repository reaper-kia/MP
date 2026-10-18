from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    grpc_address: str = "[::]:50052"

    database_url: str = "postgresql+asyncpg://example:example_local@localhost:5434/example"
    database_echo: bool = False

    # куда ходить за пользователями (межсервисный gRPC)
    auth_grpc_target: str = "localhost:50051"
    grpc_client_timeout: float = 3.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
