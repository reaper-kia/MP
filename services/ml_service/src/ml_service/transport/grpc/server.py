import asyncio
import logging

from grpc import aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection
from ml.v1 import ml_service_pb2 as pb
from ml.v1 import ml_service_pb2_grpc as pb_grpc

from ml_service.config import get_settings
from ml_service.dependencies import build_engine, warm_up
from ml_service.engine import MlEngine
from ml_service.transport.grpc.servicer import MlServicer
from ml_service.transport.http_health import start_health_server

logger = logging.getLogger(__name__)

SERVICE_NAMES = (
    pb.DESCRIPTOR.services_by_name["MlService"].full_name,
    health_pb2.DESCRIPTOR.services_by_name["Health"].full_name,
    reflection.SERVICE_NAME,
)


async def create_server(engine: MlEngine, address: str) -> tuple[aio.Server, int]:
    server = aio.server()

    pb_grpc.add_MlServiceServicer_to_server(MlServicer(engine), server)

    health_service = health.aio.HealthServicer()  # type: ignore[attr-defined]
    health_pb2_grpc.add_HealthServicer_to_server(health_service, server)
    await health_service.set("", health_pb2.HealthCheckResponse.SERVING)

    reflection.enable_server_reflection(SERVICE_NAMES, server)

    port = server.add_insecure_port(address)
    if port == 0:
        raise RuntimeError(f"Cannot bind gRPC server to {address}")

    return server, port


async def serve() -> None:
    settings = get_settings()
    engine = build_engine(settings)

    server, _ = await create_server(engine, settings.grpc_address)
    await server.start()
    logger.info("ML gRPC server listening on %s (%s)", settings.grpc_address, engine.describe)
    health = await start_health_server(settings.health_address, engine.status)
    # прогрев в фоне: сервер уже отвечает (эвристиками), пока модель грузится в память
    warm = asyncio.create_task(warm_up(engine))

    try:
        await server.wait_for_termination()
    finally:
        warm.cancel()
        if health is not None:
            health.close()
        await server.stop(grace=5)
        await engine.aclose()
