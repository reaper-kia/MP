"""Composition root: здесь реализации связываются с портами и хэндлеры — с командами."""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncEngine

from auth_service.applications.commands.login_user import LoginUserCommand
from auth_service.applications.commands.logout_user import LogoutUserCommand
from auth_service.applications.commands.refresh_token import RefreshTokenCommand
from auth_service.applications.commands.register_user import RegisterUserCommand
from auth_service.applications.handlers.get_user import GetUserQueryHandler
from auth_service.applications.handlers.login_user import LoginUserCommandHandler
from auth_service.applications.handlers.logout_user import LogoutUserCommandHandler
from auth_service.applications.handlers.refresh_token import RefreshTokenCommandHandler
from auth_service.applications.handlers.register_user import RegisterUserCommandHandler
from auth_service.applications.mediator import Mediator
from auth_service.applications.ports.password_hasher import PasswordHasher
from auth_service.applications.ports.token_service import AccessTokenIssuer, RefreshTokenService
from auth_service.applications.ports.unit_of_work import UnitOfWorkFactory
from auth_service.applications.queries.get_user import GetUserQuery
from auth_service.applications.services.token_pair_factory import TokenPairFactory
from auth_service.infra.config import Settings
from auth_service.infra.database.database import create_engine, create_session_factory
from auth_service.infra.security.password_hasher import Argon2PasswordHasher
from auth_service.infra.security.tokens import JwtAccessTokenIssuer, SecureRefreshTokenService
from auth_service.infra.uow.sqlalchemy_unit_of_work import SQLAlchemyUnitOfWorkFactory


@dataclass(frozen=True)
class Container:
    engine: AsyncEngine
    mediator: Mediator

    async def close(self) -> None:
        await self.engine.dispose()


@dataclass(frozen=True)
class AuthDeps:
    uow_factory: UnitOfWorkFactory
    password_hasher: PasswordHasher
    access_tokens: AccessTokenIssuer
    refresh_tokens: RefreshTokenService


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings)
    deps = AuthDeps(
        uow_factory=SQLAlchemyUnitOfWorkFactory(create_session_factory(engine)),
        password_hasher=Argon2PasswordHasher(),
        access_tokens=JwtAccessTokenIssuer(
            secret=settings.jwt_secret,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            ttl=timedelta(seconds=settings.access_token_ttl_seconds),
        ),
        refresh_tokens=SecureRefreshTokenService(),
    )
    return Container(engine=engine, mediator=build_mediator(settings, deps))


def build_mediator(settings: Settings, deps: AuthDeps) -> Mediator:
    """Единственное место, где сценарии привязываются к командам."""
    token_pair_factory = TokenPairFactory(
        access_tokens=deps.access_tokens,
        refresh_tokens=deps.refresh_tokens,
        refresh_token_ttl=timedelta(seconds=settings.refresh_token_ttl_seconds),
    )
    mediator = Mediator()
    mediator.register(
        RegisterUserCommand,
        RegisterUserCommandHandler(
            uow_factory=deps.uow_factory,
            password_hasher=deps.password_hasher,
            token_pair_factory=token_pair_factory,
            admin_emails=settings.admin_email_set,
        ),
    )
    mediator.register(
        LoginUserCommand,
        LoginUserCommandHandler(
            uow_factory=deps.uow_factory,
            password_hasher=deps.password_hasher,
            token_pair_factory=token_pair_factory,
        ),
    )
    mediator.register(
        RefreshTokenCommand,
        RefreshTokenCommandHandler(
            uow_factory=deps.uow_factory,
            refresh_tokens=deps.refresh_tokens,
            token_pair_factory=token_pair_factory,
        ),
    )
    mediator.register(
        LogoutUserCommand,
        LogoutUserCommandHandler(uow_factory=deps.uow_factory, refresh_tokens=deps.refresh_tokens),
    )
    mediator.register(GetUserQuery, GetUserQueryHandler(uow_factory=deps.uow_factory))
    return mediator
