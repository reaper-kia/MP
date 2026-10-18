from types import SimpleNamespace
from typing import Any

import grpc
import pytest
from grpc import aio

from platform_common.errors import ErrorDetail, ErrorKind, NotFoundError, ValidationError
from platform_common.grpc.errors import app_error_from_rpc, parse_rpc_error, rpc


class ItemNotFound(NotFoundError):
    code = "ITEM_NOT_FOUND"


class Servicer:
    @rpc
    async def NotFound(self, request: Any, context: Any) -> bytes:
        raise ItemNotFound("no item")

    @rpc
    async def Invalid(self, request: Any, context: Any) -> bytes:
        raise ValidationError("bad", details=[ErrorDetail("title", "too_long")])

    @rpc
    async def Boom(self, request: Any, context: Any) -> bytes:
        raise RuntimeError("secret internals")


async def _call(method: str) -> aio.AioRpcError:
    servicer = Servicer()

    def handler(name: str) -> grpc.RpcMethodHandler:
        fn = getattr(servicer, name)

        async def behavior(request: bytes, context: Any) -> bytes:
            return await fn(SimpleNamespace(context=SimpleNamespace(request_id="r1")), context)

        return grpc.unary_unary_rpc_method_handler(behavior)

    server = aio.server()
    server.add_generic_rpc_handlers(
        (
            grpc.method_handlers_generic_handler(
                "test.Svc", {n: handler(n) for n in ("NotFound", "Invalid", "Boom")}
            ),
        )
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        async with aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            call = channel.unary_unary(f"/test.Svc/{method}")
            with pytest.raises(aio.AioRpcError) as exc_info:
                await call(b"")
            return exc_info.value
    finally:
        await server.stop(None)


async def test_domain_error_keeps_public_code() -> None:
    info = parse_rpc_error(await _call("NotFound"))
    assert info.status == grpc.StatusCode.NOT_FOUND
    assert info.code == "ITEM_NOT_FOUND"
    assert info.message == "no item"


async def test_validation_details_roundtrip() -> None:
    exc = await _call("Invalid")
    error = app_error_from_rpc(exc)
    assert isinstance(error, ValidationError)
    assert error.kind is ErrorKind.VALIDATION
    assert error.details == [ErrorDetail("title", "too_long")]


async def test_unexpected_error_is_hidden() -> None:
    info = parse_rpc_error(await _call("Boom"))
    assert info.status == grpc.StatusCode.INTERNAL
    assert "secret" not in info.message
