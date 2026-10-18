from functools import lru_cache

from platform_common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "example"
    grpc_port: int = 50052
    database_name: str = "example"

    # Куда ходить за данными пользователей (межсервисный gRPC)
    auth_grpc_target: str = "localhost:50051"


@lru_cache
def get_settings() -> Settings:
    return Settings()
