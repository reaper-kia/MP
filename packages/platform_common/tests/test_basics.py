from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

import pytest

from platform_common.context import RequestContext
from platform_common.errors import PermissionDeniedError, UnauthenticatedError, ValidationError
from platform_common.mediator import Command, Mediator
from platform_common.pagination import Page, decode_cursor, encode_cursor
from platform_common.security.jwt import InvalidTokenError, JwtCodec


@dataclass(frozen=True)
class Double(Command[int]):
    value: int


class DoubleHandler:
    async def handle(self, request: Double) -> int:
        return request.value * 2


async def test_mediator_dispatch() -> None:
    mediator = Mediator()
    mediator.register(Double, DoubleHandler())
    assert await mediator.send(Double(21)) == 42


def test_jwt_roundtrip_and_tamper() -> None:
    codec = JwtCodec("s" * 32, ttl=timedelta(minutes=1))
    user_id = uuid4()
    issued = codec.issue(user_id, "admin")
    claims = codec.decode(issued.token)
    assert claims.user_id == user_id and claims.role == "admin"
    with pytest.raises(InvalidTokenError):
        JwtCodec("o" * 32).decode(issued.token)
    with pytest.raises(InvalidTokenError):
        JwtCodec("s" * 32, ttl=timedelta(seconds=-1)).decode(
            JwtCodec("s" * 32, ttl=timedelta(seconds=-1)).issue(user_id, "user").token
        )


def test_pagination() -> None:
    page = Page.from_request(limit=2, cursor="")
    assert page.offset == 0 and page.limit == 2
    assert page.next_cursor(fetched=3) == encode_cursor(2)
    assert page.next_cursor(fetched=2) == ""
    assert decode_cursor(encode_cursor(40)) == 40
    with pytest.raises(ValidationError):
        decode_cursor("garbage!")


def test_request_context_permissions() -> None:
    owner = uuid4()
    anon = RequestContext("r")
    with pytest.raises(UnauthenticatedError):
        anon.require_user()
    user = RequestContext("r", actor_user_id=uuid4(), actor_role="user")
    with pytest.raises(PermissionDeniedError):
        user.require_owner_or_admin(owner)
    admin = RequestContext("r", actor_user_id=uuid4(), actor_role="admin")
    admin.require_owner_or_admin(owner)
    assert RequestContext.from_proto(admin.to_proto()) == admin
