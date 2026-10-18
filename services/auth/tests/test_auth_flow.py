from uuid import uuid4

import pytest

from auth_service.application.commands.login_user import LoginUser
from auth_service.application.commands.logout_user import LogoutUser
from auth_service.application.commands.refresh_tokens import RefreshTokens
from auth_service.application.commands.register_user import USER_REGISTERED, RegisterUser
from auth_service.application.queries.get_user import GetUser
from auth_service.domain.errors import (
    EmailTakenError,
    InvalidCredentialsError,
    InvalidEmailError,
    InvalidRefreshTokenError,
    WeakPasswordError,
)
from auth_service.domain.user import Role
from platform_common.context import RequestContext
from platform_common.errors import UnauthenticatedError
from platform_common.mediator import Mediator
from tests.fakes import FakeDb

ANON = RequestContext("test")


async def register(mediator: Mediator, email: str = "Alice@Example.com"):
    return await mediator.send(RegisterUser(ANON, email, "Alice", "password123"))


async def test_register_creates_user_session_and_event(mediator: Mediator, db: FakeDb) -> None:
    result = await register(mediator)
    assert result.user.email == "alice@example.com"
    assert result.user.role is Role.USER
    assert len(db.users) == 1 and len(db.sessions) == 1
    assert [e[1] for e in db.events] == [USER_REGISTERED]


async def test_admin_email_gets_admin_role(mediator: Mediator) -> None:
    result = await register(mediator, "boss@example.com")
    assert result.user.role is Role.ADMIN


async def test_register_validation(mediator: Mediator) -> None:
    with pytest.raises(InvalidEmailError):
        await mediator.send(RegisterUser(ANON, "nope", "A", "password123"))
    with pytest.raises(WeakPasswordError):
        await mediator.send(RegisterUser(ANON, "a@b.co", "A", "short"))


async def test_duplicate_email(mediator: Mediator, db: FakeDb) -> None:
    await register(mediator)
    with pytest.raises(EmailTakenError):
        await register(mediator, "alice@example.com")
    assert len(db.users) == 1


async def test_login(mediator: Mediator) -> None:
    await register(mediator)
    result = await mediator.send(LoginUser(ANON, "alice@example.com", "password123"))
    assert result.tokens.access_token
    with pytest.raises(InvalidCredentialsError):
        await mediator.send(LoginUser(ANON, "alice@example.com", "wrong-password"))
    with pytest.raises(InvalidCredentialsError):
        await mediator.send(LoginUser(ANON, "ghost@example.com", "password123"))


async def test_refresh_rotates_and_old_token_dies(mediator: Mediator) -> None:
    old = (await register(mediator)).tokens.refresh_token
    new = await mediator.send(RefreshTokens(ANON, old))
    assert new.refresh_token != old
    with pytest.raises(InvalidRefreshTokenError):
        await mediator.send(RefreshTokens(ANON, old))
    await mediator.send(LogoutUser(ANON, new.refresh_token))
    await mediator.send(LogoutUser(ANON, new.refresh_token))  # идемпотентно
    with pytest.raises(InvalidRefreshTokenError):
        await mediator.send(RefreshTokens(ANON, new.refresh_token))


async def test_get_user_hides_foreign_email(mediator: Mediator) -> None:
    alice = (await register(mediator)).user
    bob = (await register(mediator, "bob@example.com")).user
    as_bob = RequestContext("t", actor_user_id=bob.id, actor_role="user")
    assert (await mediator.send(GetUser(as_bob, None))).email == "bob@example.com"
    assert (await mediator.send(GetUser(as_bob, alice.id))).email == ""
    with pytest.raises(UnauthenticatedError):
        await mediator.send(GetUser(ANON, alice.id))
    with pytest.raises(Exception, match="not found"):
        await mediator.send(GetUser(as_bob, uuid4()))
