import logging

from grpc import aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection
from search.v1 import search_service_pb2 as pb
from search.v1 import search_service_pb2_grpc as pb_grpc

from search_service.applications.mediator import Mediator
from search_service.dependencies import build_container
from search_service.infra.config import get_settings
from search_service.transport.grpc.servicer import SearchServicer

logger = logging.getLogger(__name__)

SERVICE_NAMES = (
    pb.DESCRIPTOR.services_by_name["SearchService"].full_name,
    health_pb2.DESCRIPTOR.services_by_name["Health"].full_name,
    reflection.SERVICE_NAME,
)


async def create_server(mediator: Mediator, address: str) -> tuple[aio.Server, int]:
    server = aio.server()

    pb_grpc.add_SearchServiceServicer_to_server(SearchServicer(mediator), server)

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
    container = build_container(settings)

    server, _ = await create_server(container.mediator, settings.grpc_address)
    await server.start()
    logger.info("Search gRPC server listening on %s", settings.grpc_address)

    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=5)
        await container.close()
