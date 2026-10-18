from dataclasses import dataclass

from auth_service.applications.commands.refresh_token import RefreshTokenCommand
from auth_service.applications.exceptions import RefreshTokenInvalidError
from auth_service.applications.ports.token_service import RefreshTokenService
from auth_service.applications.ports.unit_of_work import UnitOfWorkFactory
from auth_service.applications.results.authentication import TokenPairResult
from auth_service.applications.services.token_pair_factory import TokenPairFactory
from auth_service.domain.entities import utc_now


@dataclass
class RefreshTokenCommandHandler:
    """Ротация: старая сессия отзывается, выдаётся новая пара токенов."""

    uow_factory: UnitOfWorkFactory
    refresh_tokens: RefreshTokenService
    token_pair_factory: TokenPairFactory

    async def handle(self, cmd: RefreshTokenCommand) -> TokenPairResult:
        if not cmd.refresh_token:
            raise RefreshTokenInvalidError("Refresh token is missing")
        token_hash = self.refresh_tokens.hash(cmd.refresh_token)

        async with self.uow_factory() as uow:
            session = await uow.refresh_sessions.get_by_token_hash_for_update(token_hash)
            if session is None or not session.is_active():
                raise RefreshTokenInvalidError("Refresh token is invalid or expired")

            user = await uow.users.get_by_id(session.user_id)
            if user is None:
                raise RefreshTokenInvalidError("Refresh token is invalid or expired")

            session.revoke()
            await uow.refresh_sessions.save(session)

            created = self.token_pair_factory.create(user=user, now=utc_now())
            await uow.refresh_sessions.add(created.refresh_session)
            await uow.commit()

        return created.tokens
