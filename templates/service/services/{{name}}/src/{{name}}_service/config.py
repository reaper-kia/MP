from functools import lru_cache

from platform_common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "{{name}}"
    grpc_port: int = {{port}}
    database_name: str = "{{name}}"
    # Нужен другой сервис? Добавь его адрес, например:
    # auth_grpc_target: str = "localhost:50051"


@lru_cache
def get_settings() -> Settings:
    return Settings()
