from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# grpc — боевые соседи (collector_service, ml_service);
# stub — офлайн-разработка без соседей: фикстуры infra/collector_stub.py, infra/ml_client.py
ClientMode = Literal["grpc", "stub"]


class Settings(BaseSettings):
    grpc_address: str = "[::]:50053"

    database_url: str = "postgresql+asyncpg://search:search_local@localhost:5435/search"
    database_echo: bool = False

    # соседи (межсервисный gRPC)
    collector_grpc_target: str = "localhost:50054"
    ml_grpc_target: str = "localhost:50055"

    # по умолчанию — настоящие gRPC-клиенты; stub включается только явно
    collector_mode: ClientMode = "grpc"
    ml_mode: ClientMode = "grpc"
    stub_fail_platforms: str = ""  # "ok,max" — какие площадки стаб коллектора «роняет»

    # таймауты вызовов, секунды
    collector_resolve_timeout: float = 20.0
    collector_collect_timeout: float = 60.0
    # больше бюджета AnalyzeQuery в ml_service (20 с): ml успевает отдать хотя бы эвристику
    ml_analyze_timeout: float = 25.0
    ml_score_timeout: float = 60.0
    ml_group_timeout: float = 60.0
    # ML без моделей (эвристики) → предупреждение «ML работал в упрощённом режиме» у поиска.
    # false — не показываем (решение TL, ML-15). Критерии требуют отделять работающее от
    # имитации: на демо держать true или проговорить на защите
    ml_show_degraded_warning: bool = True

    # пайплайн (B2-04)
    collect_concurrency: int = 5
    # очередь поисков (B2-15): сколько поисков идёт одновременно, остальные ждут в queued
    search_max_parallel: int = 1
    target_timeout: int = 60  # одна цель (источник / площадка) целиком

    # кэш готовых подборок в Redis (B2-20). false — всё как до кэша
    cache_enabled: bool = True
    redis_url: str = "redis://localhost:6379/0"
    redis_timeout_seconds: float = 0.2
    cache_search_ttl_seconds: int = 1800

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
