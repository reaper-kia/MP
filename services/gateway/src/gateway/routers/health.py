import asyncio

import grpc
from fastapi import APIRouter
from grpc_health.v1 import health_pb2, health_pb2_grpc

from gateway.dependencies import Clients

router = APIRouter(tags=["health"])

REDIS_HEALTH_NAME = "redis"  # имя в gRPC health search_service (transport/grpc/server.py)


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


async def check(channel: object, service: str = "") -> str:
    stub = health_pb2_grpc.HealthStub(channel)
    try:
        response = await stub.Check(health_pb2.HealthCheckRequest(service=service), timeout=1.5)  # type: ignore[attr-defined]
    except grpc.aio.AioRpcError as e:
        # search_service не публикует «redis», когда кэш выключен (CACHE_ENABLED=false)
        return "off" if service and e.code() == grpc.StatusCode.NOT_FOUND else "down"
    except Exception:
        return "down"
    return "up" if response.status == health_pb2.HealthCheckResponse.SERVING else "down"


@router.get("/health/ready")
async def ready(clients: Clients) -> dict[str, object]:
    """Опрашивает gRPC health каждого сервиса. redis (кэш, B2-20) — up / down / off; на status
    не влияет: без кэша поиск работает, только медленнее."""
    names = list(clients.channels)
    checks = [check(clients.channels[n]) for n in names]
    search = clients.channels.get("search")
    redis_check = check(search, REDIS_HEALTH_NAME) if search is not None else _off()
    *results, redis = await asyncio.gather(*checks, redis_check)
    services = dict(zip(names, results, strict=True))
    status = "ok" if all(v == "up" for v in services.values()) else "degraded"
    return {"status": status, "services": services, "redis": redis}


async def _off() -> str:
    return "off"
