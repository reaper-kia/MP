from dataclasses import dataclass

from auth_service.application.dto import Tokens
from auth_service.application.ports import TokenService, UnitOfWorkFactory
from auth_service.application.tokens import SessionIssuer
from auth_service.domain.errors import InvalidRefreshTokenError
from platform_common.context import RequestContext
from platform_common.mediator import Command


@dataclass(frozen=True, slots=True)
class RefreshTokens(Command[Tokens]):
    ctx: RequestContext
    refresh_token: str


class RefreshTokensHandler:
    """Ротация: старая сессия отзывается, выдаётся новая пара."""

    def __init__(
        self, uow_factory: UnitOfWorkFactory, tokens: TokenService, issuer: SessionIssuer
    ) -> None:
        self._uow_factory = uow_factory
        self._tokens = tokens
        self._issuer = issuer

    async def handle(self, cmd: RefreshTokens) -> Tokens:
        if not cmd.refresh_token:
            raise InvalidRefreshTokenError()
        token_hash = self._tokens.hash_refresh_token(cmd.refresh_token)

        async with self._uow_factory() as uow:
            session = await uow.sessions.get_by_token_hash(token_hash)
            if session is None or not session.is_active():
                raise InvalidRefreshTokenError()
            user = await uow.users.get(session.user_id)
            if user is None:
                raise InvalidRefreshTokenError()
            session.revoke()
            await uow.sessions.update(session)
            tokens = await self._issuer.issue(uow, user)
            await uow.commit()
        return tokens
