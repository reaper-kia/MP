"""Gateway без настоящих сервисов: gRPC-стабы подменены фейками."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import grpc
import httpx
import jwt
import pytest
from auth.v1 import auth_service_pb2 as auth_pb
from example.v1 import example_service_pb2 as example_pb
from google.protobuf.timestamp_pb2 import Timestamp

from gateway.config import Settings, get_settings
from gateway.main import create_app

SETTINGS = Settings(jwt_secret="test-secret-test-secret-test-secret-123")
USER_ID = uuid4()


def ts(value: datetime) -> Timestamp:
    t = Timestamp()
    t.FromDatetime(value)
    return t


def grpc_error(
    status: grpc.StatusCode, message: str, code: str | None = None
) -> grpc.aio.AioRpcError:
    trailing = grpc.aio.Metadata(("error-code", code)) if code else grpc.aio.Metadata()
    return grpc.aio.AioRpcError(status, grpc.aio.Metadata(), trailing, details=message)


class FakeAuth:
    async def Login(self, req: auth_pb.LoginRequest) -> auth_pb.LoginResponse:
        if req.password != "password123":
            raise grpc_error(grpc.StatusCode.UNAUTHENTICATED, "bad", "INVALID_CREDENTIALS")
        now = datetime.now(UTC)
        return auth_pb.LoginResponse(
            user=auth_pb.User(
                id=str(USER_ID),
                email=req.email,
                name="A",
                role=auth_pb.USER_ROLE_USER,
                created_at=ts(now),
            ),
            tokens=auth_pb.TokenPair(
                access_token="acc",
                refresh_token="ref",
                access_expires_at=ts(now + timedelta(minutes=15)),
                refresh_expires_at=ts(now + timedelta(days=1)),
            ),
        )


class FakeExample:
    last_context: Any = None

    async def GetItem(self, req: example_pb.GetItemRequest) -> example_pb.GetItemResponse:
        self.last_context = req.context
        raise grpc_error(grpc.StatusCode.NOT_FOUND, "Item not found", "ITEM_NOT_FOUND")

    async def ListItems(self, req: example_pb.ListItemsRequest) -> example_pb.ListItemsResponse:
        raise grpc_error(grpc.StatusCode.UNAVAILABLE, "connection refused")


class FakeClients:
    def __init__(self) -> None:
        self.auth = FakeAuth()
        self.example = FakeExample()
        self.channels: dict[str, Any] = {}


@pytest.fixture
async def client() -> AsyncIterator[tuple[httpx.AsyncClient, FakeClients]]:
    fakes = FakeClients()
    app = create_app(SETTINGS, fakes)  # type: ignore[arg-type]
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, fakes


def bearer() -> dict[str, str]:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(USER_ID),
            "role": "user",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": SETTINGS.jwt_issuer,
            "aud": SETTINGS.jwt_audience,
        },
        SETTINGS.jwt_secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


async def test_login_sets_httponly_refresh_cookie(client: Any) -> None:
    c, _ = client
    r = await c.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["access_token"] == "acc"
    assert "refresh_token=ref" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]


async def test_grpc_error_keeps_service_code(client: Any) -> None:
    c, fakes = client
    r = await c.get(f"/api/v1/items/{uuid4()}", headers={**bearer(), "X-Request-ID": "req-1"})
    assert r.status_code == 404
    assert r.json()["error"] == {
        "code": "ITEM_NOT_FOUND",
        "message": "Item not found",
        "request_id": "req-1",
        "details": [],
    }
    # gateway сам заполнил контекст из JWT
    assert fakes.example.last_context.actor_user_id == str(USER_ID)
    assert fakes.example.last_context.request_id == "req-1"


async def test_unavailable_is_503(client: Any) -> None:
    c, _ = client
    r = await c.get("/api/v1/items", headers=bearer())
    assert r.status_code == 503 and r.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


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
    assert r.json()["error"]["details"][0]["field"] == "item_id"


async def test_wrong_password(client: Any) -> None:
    c, _ = client
    r = await c.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "x"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
