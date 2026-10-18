import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gateway.clients import GrpcClients
from gateway.config import Settings, get_settings
from gateway.errors import register_error_handlers
from gateway.middleware import RequestIdMiddleware
from gateway.routers import auth, health, items, users

# >>> router imports (new_service.py вставляет строки выше)
from gateway.ws import router as ws_router
from gateway.ws.manager import ConnectionManager
from platform_common.logging import setup_logging
from platform_common.redis import create_redis
from platform_common.security.jwt import JwtCodec

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, clients: GrpcClients | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        own_clients = clients is None
        app.state.clients = clients or GrpcClients(settings)
        app.state.redis = create_redis(settings.redis_url)
        logger.info("Gateway started")
        try:
            yield
        finally:
            if own_clients:
                await app.state.clients.close()
            await app.state.redis.aclose()

    app = FastAPI(title="MP Gateway", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.jwt = JwtCodec(settings.jwt_secret, ttl=timedelta(minutes=15))
    app.state.ws = ConnectionManager()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(items.router)
    # >>> routers (new_service.py вставляет строки выше)
    app.include_router(ws_router.router)
    return app


def run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.service_name)
    uvicorn.run(
        "gateway.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_config=None,
    )


if __name__ == "__main__":
    run()
