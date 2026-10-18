"""Запуск gRPC-сервера: health + reflection + graceful shutdown + фоновые задачи.

await run_grpc_server(
    address=settings.grpc_address,
    bindings=[bind(pb_grpc.add_ExampleServiceServicer_to_server, servicer, pb, "ExampleService")],
    background=[relay.run],          # опционально: outbox relay, kafka consumer...
    on_shutdown=container.close,
)
"""

import asyncio
import contextlib
import logging
import signal
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from google.protobuf.descriptor import FileDescriptor
from grpc import aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ServicerBinding:
    add_to_server: Callable[[Any, aio.Server], None]
    servicer: object
    full_name: str


def bind(
    add_to_server: Callable[[Any, aio.Server], None],
    servicer: object,
    pb_module: Any,
    service: str,
) -> ServicerBinding:
    descriptor: FileDescriptor = pb_module.DESCRIPTOR
    return ServicerBinding(add_to_server, servicer, descriptor.services_by_name[service].full_name)


async def create_server(
    bindings: Sequence[ServicerBinding], address: str
) -> tuple[aio.Server, int, Any]:
    server = aio.server(
        options=[
            ("grpc.keepalive_time_ms", 30_000),
            ("grpc.keepalive_permit_without_calls", 1),
        ]
    )
    for b in bindings:
        b.add_to_server(b.servicer, server)

    health_servicer = health.aio.HealthServicer()  # type: ignore[attr-defined]
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

    names = [b.full_name for b in bindings]
    names += [health_pb2.DESCRIPTOR.services_by_name["Health"].full_name, reflection.SERVICE_NAME]
    reflection.enable_server_reflection(names, server)

    port = server.add_insecure_port(address)
    if port == 0:
        raise RuntimeError(f"Cannot bind gRPC server to {address}")
    return server, port, health_servicer


async def run_grpc_server(
    *,
    address: str,
    bindings: Sequence[ServicerBinding],
    background: Sequence[Callable[[], Awaitable[None]]] = (),
    on_shutdown: Callable[[], Awaitable[None]] | None = None,
    grace: float = 5.0,
) -> None:
    server, _, health_servicer = await create_server(bindings, address)
    await server.start()
    logger.info(
        "gRPC server listening on %s (%s)", address, ", ".join(b.full_name for b in bindings)
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    tasks = [
        asyncio.create_task(_supervise(job), name=getattr(job, "__qualname__", "job"))
        for job in background
    ]
    try:
        await stop.wait()
    finally:
        logger.info("Shutting down...")
        await health_servicer.enter_graceful_shutdown()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await server.stop(grace)
        if on_shutdown is not None:
            await on_shutdown()


async def _supervise(job: Callable[[], Awaitable[None]]) -> None:
    """Фоновая задача не должна валить сервер: падение → лог и перезапуск."""
    name = getattr(job, "__qualname__", repr(job))
    while True:
        try:
            await job()
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Background job %s crashed, restarting in 3s", name)
            await asyncio.sleep(3)
