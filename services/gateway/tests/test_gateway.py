"""Gateway без реальных сервисов: gRPC-стабы подменены фейками."""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import grpc
import httpx
import pytest
from grpc import aio

from contracts.auth.v1 import auth_pb2
from contracts.example.v1 import example_pb2
from gateway.config import Settings
from gateway.main import create_app
from platform_common.security.jwt import JwtCodec
from platform_common.time import to_timestamp, utcnow

SECRET = "test-secret-test-secret-test-secret-123"
USER_ID = uuid4()


def rpc_error(status: grpc.StatusCode, message: str, code: str | None = None) -> aio.AioRpcError:
    trailing = aio.Metadata(("x-error-code", code)) if code else aio.Metadata()
    return aio.AioRpcError(status, aio.Metadata(), trailing, details=message)


class FakeAuth:
    async def Login(self, req: auth_pb2.LoginRequest) -> auth_pb2.LoginResponse:
        if req.password != "password123":
            raise rpc_error(grpc.StatusCode.UNAUTHENTICATED, "bad", "INVALID_CREDENTIALS")
        now = utcnow()
        return auth_pb2.LoginResponse(
            user=auth_pb2.User(
                id=str(USER_ID),
                email=req.email,
                name="A",
                role=auth_pb2.USER_ROLE_USER,
                created_at=to_timestamp(now),
            ),
            tokens=auth_pb2.TokenPair(
                access_token="acc",
                refresh_token="ref",
                access_expires_at=to_timestamp(now + timedelta(minutes=15)),
                refresh_expires_at=to_timestamp(now + timedelta(days=1)),
            ),
        )


class FakeExample:
    def __init__(self) -> None:
        self.last_context: Any = None

    async def GetItem(self, req: example_pb2.GetItemRequest) -> example_pb2.GetItemResponse:
        self.last_context = req.context
        raise rpc_error(grpc.StatusCode.NOT_FOUND, "Item not found", "ITEM_NOT_FOUND")

    async def ListItems(self, req: example_pb2.ListItemsRequest) -> example_pb2.ListItemsResponse:
        raise rpc_error(grpc.StatusCode.UNAVAILABLE, "connection refused")


class FakeClients:
    def __init__(self) -> None:
        self.auth = FakeAuth()
        self.example = FakeExample()

    def names(self) -> list[str]:
        return []


@pytest.fixture
async def client() -> AsyncIterator[tuple[httpx.AsyncClient, FakeClients]]:
    fakes = FakeClients()
    app = create_app(Settings(jwt_secret=SECRET, redis_url="redis://127.0.0.1:1/0"), fakes)  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, fakes


def bearer() -> dict[str, str]:
    token = JwtCodec(SECRET).issue(USER_ID, "user").token
    return {"Authorization": f"Bearer {token}"}


async def test_login_sets_httponly_refresh_cookie(client: Any) -> None:
    c, _ = client
    r = await c.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["access_token"] == "acc"
    cookie = r.headers["set-cookie"]
    assert "refresh_token=ref" in cookie and "HttpOnly" in cookie
    assert r.headers["x-request-id"]


async def test_grpc_error_mapped_with_domain_code(client: Any) -> None:
    c, fakes = client
    r = await c.get(f"/api/v1/items/{uuid4()}", headers={**bearer(), "X-Request-ID": "req-1"})
    assert r.status_code == 404
    assert r.json()["error"] == {
        "code": "ITEM_NOT_FOUND",
        "message": "Item not found",
        "request_id": "req-1",
        "details": [],
    }
    # Gateway сам заполнил контекст из JWT
    assert fakes.example.last_context.actor_user_id == str(USER_ID)
    assert fakes.example.last_context.request_id == "req-1"


async def test_unavailable_is_503(client: Any) -> None:
    c, _ = client
    r = await c.get("/api/v1/items", headers=bearer())
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


async def test_auth_required_and_bad_token(client: Any) -> None:
    c, _ = client
    r = await c.get("/api/v1/items")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"
    r = await c.get("/api/v1/items", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_TOKEN"


async def test_validation_error_format(client: Any) -> None:
    c, _ = client
    r = await c.get("/api/v1/items/not-a-uuid", headers=bearer())
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"][0]["field"] == "item_id"


async def test_wrong_password(client: Any) -> None:
    c, _ = client
    r = await c.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "x"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
