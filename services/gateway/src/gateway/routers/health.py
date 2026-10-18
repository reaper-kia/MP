import asyncio

from fastapi import APIRouter
from grpc_health.v1 import health_pb2, health_pb2_grpc

from gateway.dependencies import Clients

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(clients: Clients) -> dict[str, object]:
    """Опрашивает gRPC health каждого сервиса."""

    async def check(channel: object) -> str:
        stub = health_pb2_grpc.HealthStub(channel)
        try:
            response = await stub.Check(health_pb2.HealthCheckRequest(), timeout=1.5)  # type: ignore[attr-defined]
        except Exception:
            return "down"
        return "up" if response.status == health_pb2.HealthCheckResponse.SERVING else "down"

    names = list(clients.channels)
    results = await asyncio.gather(*(check(clients.channels[n]) for n in names))
    services = dict(zip(names, results, strict=True))
    status = "ok" if all(v == "up" for v in services.values()) else "degraded"
    return {"status": status, "services": services}
