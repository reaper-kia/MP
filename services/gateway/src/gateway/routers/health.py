import asyncio

from fastapi import APIRouter, Request
from grpc_health.v1 import health_pb2, health_pb2_grpc

from gateway.dependencies import Clients

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request, clients: Clients) -> dict[str, object]:
    """Проверяет gRPC health всех сервисов и Redis. Удобно для `make smoke`."""

    async def check(channel: object) -> str:
        stub = health_pb2_grpc.HealthStub(channel)
        try:
            resp = await stub.Check(health_pb2.HealthCheckRequest(), timeout=1.5)  # type: ignore[attr-defined]
        except Exception:
            return "down"
        return "up" if resp.status == health_pb2.HealthCheckResponse.SERVING else "down"

    names = clients.names()
    results = await asyncio.gather(*(check(clients.channel(n)) for n in names))
    services = dict(zip(names, results, strict=True))
    redis = request.app.state.redis
    try:
        services["redis"] = "up" if await redis.ping() else "down"
    except Exception:
        services["redis"] = "down"
    status = "ok" if all(v == "up" for v in services.values()) else "degraded"
    return {"status": status, "services": services}
