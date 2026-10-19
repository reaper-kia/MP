from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "search_service"
    grpc_port: int = 50051
    http_port: int = 8100

    collector_mode: str = "stub"  # stub | grpc
    ml_mode: str = "stub"  # stub | grpc
    stub_fail_platforms: str = ""  # "ok,max" — какие площадки стаб «роняет»

    # DB
    database_url: str = "postgresql+asyncpg://search:search@db:5432/search"

    # Siblings
    collector_grpc: str = "collector:50052"
    ml_grpc: str = "ml:50053"

    # Timeouts
    target_timeout_sec: int = 60
    ml_batch_timeout_sec: int = 60
    collect_concurrency: int = 5
    ml_batch_size: int = 30
    ml_concurrent_batches: int = 3

    # Business
    max_period_days: int = 366
    min_query_len: int = 3

    model_config = SettingsConfigDict(env_prefix="SEARCH_")
