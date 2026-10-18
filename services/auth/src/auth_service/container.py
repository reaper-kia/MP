"""Composition root: единственное место, где реализации связываются с портами."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncEngine

from auth_service.application.commands.login_user import LoginUser, LoginUserHandler
from auth_service.application.commands.logout_user import LogoutUser, LogoutUserHandler
from auth_service.application.commands.refresh_tokens import RefreshTokens, RefreshTokensHandler
from auth_service.application.commands.register_user import RegisterUser, RegisterUserHandler
from auth_service.application.ports import PasswordHasher, TokenService, UnitOfWorkFactory
from auth_service.application.queries.get_user import GetUser, GetUserHandler
from auth_service.application.tokens import SessionIssuer
from auth_service.config import Settings
from auth_service.infra.db.models import OutboxMessage
from auth_service.infra.security import Argon2PasswordHasher, JwtTokenService
from auth_service.infra.uow import SqlAlchemyAuthUnitOfWork
from platform_common.db.engine import create_engine, create_session_factory
from platform_common.kafka.outbox import OutboxRelay
from platform_common.kafka.producer import KafkaPublisher
from platform_common.mediator import Mediator
from platform_common.security.jwt import JwtCodec


@dataclass
class Container:
    engine: AsyncEngine
    mediator: Mediator
    background: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def close(self) -> None:
        await self.engine.dispose()


def build_mediator(
    settings: Settings,
    uow_factory: UnitOfWorkFactory,
    hasher: PasswordHasher,
    tokens: TokenService,
) -> Mediator:
    issuer = SessionIssuer(tokens, timedelta(seconds=settings.refresh_token_ttl_seconds))
    mediator = Mediator()
    mediator.register(
        RegisterUser, RegisterUserHandler(uow_factory, hasher, issuer, settings.admin_email_set)
    )
    mediator.register(LoginUser, LoginUserHandler(uow_factory, hasher, issuer))
    mediator.register(RefreshTokens, RefreshTokensHandler(uow_factory, tokens, issuer))
    mediator.register(LogoutUser, LogoutUserHandler(uow_factory, tokens))
    mediator.register(GetUser, GetUserHandler(uow_factory))
    return mediator


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings.database_url, echo=settings.database_echo)
    session_factory = create_session_factory(engine)

    def uow_factory() -> SqlAlchemyAuthUnitOfWork:
        return SqlAlchemyAuthUnitOfWork(session_factory)

    codec = JwtCodec(settings.jwt_secret, ttl=timedelta(seconds=settings.access_token_ttl_seconds))
    mediator = build_mediator(settings, uow_factory, Argon2PasswordHasher(), JwtTokenService(codec))

    container = Container(engine=engine, mediator=mediator)
    if settings.kafka_enabled:
        relay = OutboxRelay(
            session_factory, OutboxMessage, KafkaPublisher(settings.kafka_bootstrap_servers)
        )
        container.background.append(relay.run)
    return container
