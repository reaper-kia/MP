from uuid import uuid4

import pytest

from auth_service.applications.commands.login_user import LoginUserCommand
from auth_service.applications.commands.logout_user import LogoutUserCommand
from auth_service.applications.commands.refresh_token import RefreshTokenCommand
from auth_service.applications.commands.register_user import RegisterUserCommand
from auth_service.applications.context import RequestContext
from auth_service.applications.exceptions import (
    InvalidCredentialsError,
    RefreshTokenInvalidError,
    UnauthenticatedError,
    UserNotFoundError,
)
from auth_service.applications.mediator import Mediator
from auth_service.applications.queries.get_user import GetUserQuery
from auth_service.domain.exceptions import (
    InvalidEmailError,
    UserAlreadyRegisterError,
    WeakPasswordError,
)
from tests.fakes import FakeDb

ANON = RequestContext(request_id="test")


async def register(mediator: Mediator, email: str = "Alice@Example.com"):
    return await mediator.send(RegisterUserCommand(ANON, email, "Alice", "password123"))


async def test_register(mediator: Mediator, db: FakeDb) -> None:
    result = await register(mediator)
    assert result.user.email == "alice@example.com"
    assert result.user.role == "user"
    assert len(db.users) == 1 and len(db.sessions) == 1


async def test_admin_email_gets_admin_role(mediator: Mediator) -> None:
    assert (await register(mediator, "boss@example.com")).user.role == "admin"


async def test_register_validation(mediator: Mediator) -> None:
    with pytest.raises(InvalidEmailError):
        await mediator.send(RegisterUserCommand(ANON, "nope", "A", "password123"))
    with pytest.raises(WeakPasswordError):
        await mediator.send(RegisterUserCommand(ANON, "a@b.co", "A", "short"))


async def test_duplicate_email(mediator: Mediator) -> None:
    await register(mediator)
    with pytest.raises(UserAlreadyRegisterError):
        await register(mediator, "alice@example.com")


async def test_login(mediator: Mediator) -> None:
    await register(mediator)
    result = await mediator.send(LoginUserCommand(ANON, "alice@example.com", "password123"))
    assert result.tokens.access_token
    with pytest.raises(InvalidCredentialsError):
        await mediator.send(LoginUserCommand(ANON, "alice@example.com", "wrong-password"))
    with pytest.raises(InvalidCredentialsError):
        await mediator.send(LoginUserCommand(ANON, "ghost@example.com", "password123"))


async def test_refresh_rotates_token(mediator: Mediator) -> None:
    old = (await register(mediator)).tokens.refresh_token
    new = await mediator.send(RefreshTokenCommand(ANON, old))
    assert new.refresh_token != old
    with pytest.raises(RefreshTokenInvalidError):
        await mediator.send(RefreshTokenCommand(ANON, old))  # старый больше не работает

    await mediator.send(LogoutUserCommand(ANON, new.refresh_token))
    await mediator.send(LogoutUserCommand(ANON, new.refresh_token))  # повтор — не ошибка
    with pytest.raises(RefreshTokenInvalidError):
        await mediator.send(RefreshTokenCommand(ANON, new.refresh_token))


async def test_get_user_hides_foreign_email(mediator: Mediator) -> None:
    alice = (await register(mediator)).user
    bob = (await register(mediator, "bob@example.com")).user
    as_bob = RequestContext("t", actor_user_id=bob.id, actor_role="user")

    assert (await mediator.send(GetUserQuery(as_bob, None))).email == "bob@example.com"
    assert (await mediator.send(GetUserQuery(as_bob, alice.id))).email == ""
    with pytest.raises(UnauthenticatedError):
        await mediator.send(GetUserQuery(ANON, alice.id))
    with pytest.raises(UserNotFoundError):
        await mediator.send(GetUserQuery(as_bob, uuid4()))
