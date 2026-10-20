import asyncio
import logging
from typing import Any

from grpc import aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection
from search.v1 import search_service_pb2 as pb
from search.v1 import search_service_pb2_grpc as pb_grpc

from search_service.applications.mediator import Mediator
from search_service.applications.ports.search_cache import SearchCache
from search_service.dependencies import build_container, mark_interrupted_searches
from search_service.infra.config import get_settings
from search_service.transport.grpc.servicer import SearchServicer

logger = logging.getLogger(__name__)
_background: set[asyncio.Task[None]] = set()

SERVICE_NAMES = (
    pb.DESCRIPTOR.services_by_name["SearchService"].full_name,
    health_pb2.DESCRIPTOR.services_by_name["Health"].full_name,
    reflection.SERVICE_NAME,
)


REDIS_HEALTH_NAME = "redis"  # gRPC health «redis»: gateway кладёт его в /health/ready
REDIS_HEALTH_PERIOD = 10.0


async def watch_redis(health_service: Any, cache: SearchCache) -> None:
    """Раз в 10 с пингуем Redis и пишем итог в gRPC health «redis» (B2-20). Готовность сервиса
    («») от Redis не зависит: без кэша поиск работает. Кэш выключен — «redis» не публикуем."""
    serving = health_pb2.HealthCheckResponse.SERVING
    not_serving = health_pb2.HealthCheckResponse.NOT_SERVING
    last: bool | None = None
    while True:
        up = await cache.ping()
        if up != last:
            if not up:
                logger.warning("cache unavailable: Redis не отвечает, поиск идёт без кэша")
            elif last is not None:
                logger.info("Redis снова отвечает, кэш подборок работает")
            last = up
        await health_service.set(REDIS_HEALTH_NAME, serving if up else not_serving)
        await asyncio.sleep(REDIS_HEALTH_PERIOD)


async def create_server(
    mediator: Mediator, address: str, cache: SearchCache | None = None
) -> tuple[aio.Server, int]:
    server = aio.server()

    pb_grpc.add_SearchServiceServicer_to_server(SearchServicer(mediator), server)

    health_service = health.aio.HealthServicer()  # type: ignore[attr-defined]
    health_pb2_grpc.add_HealthServicer_to_server(health_service, server)
    await health_service.set("", health_pb2.HealthCheckResponse.SERVING)
    if cache is not None and cache.enabled:
        task = asyncio.create_task(watch_redis(health_service, cache))
        _background.add(task)
        task.add_done_callback(_background.discard)

    reflection.enable_server_reflection(SERVICE_NAMES, server)

    port = server.add_insecure_port(address)
    if port == 0:
        raise RuntimeError(f"Cannot bind gRPC server to {address}")

    return server, port


async def serve() -> None:
    settings = get_settings()
    container = build_container(settings)

    try:
        await mark_interrupted_searches(container.uow)
    except Exception:
        # БД ещё не готова или нет миграций — сервер всё равно поднимаем, ошибка будет в RPC
        logger.exception("Не удалось пометить прерванные поиски")

    server, _ = await create_server(container.mediator, settings.grpc_address, container.cache)
    await server.start()
    logger.info(
        "Search gRPC server listening on %s (collector=%s, ml=%s)",
        settings.grpc_address,
        settings.collector_mode,
        settings.ml_mode,
    )

    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=5)
        await container.close()
