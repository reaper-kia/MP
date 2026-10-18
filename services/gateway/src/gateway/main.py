import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from gateway.config import Settings, get_settings
from gateway.errors import register_error_handlers
from gateway.grpc_clients import GrpcClients
from gateway.routers import auth, health, items, users
from gateway.ws import ConnectionManager
from gateway.ws import router as ws_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None, clients: GrpcClients | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.clients = clients or GrpcClients(settings)
        try:
            yield
        finally:
            if clients is None:
                await app.state.clients.close()

    app = FastAPI(title="MP Gateway", version="0.1.0", lifespan=lifespan)
    app.state.ws = ConnectionManager()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """X-Request-ID от клиента или новый — уходит в RequestContext и в ответ."""
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id[:128]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(items.router)
    app.include_router(ws_router)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("gateway.main:app", host="0.0.0.0", port=8000, proxy_headers=True)
