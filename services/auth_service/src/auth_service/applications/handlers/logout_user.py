from dataclasses import dataclass

from auth_service.applications.commands.logout_user import LogoutUserCommand
from auth_service.applications.ports.token_service import RefreshTokenService
from auth_service.applications.ports.unit_of_work import UnitOfWorkFactory


@dataclass
class LogoutUserCommandHandler:
    """Идемпотентно: неизвестный или уже отозванный токен — не ошибка."""

    uow_factory: UnitOfWorkFactory
    refresh_tokens: RefreshTokenService

    async def handle(self, cmd: LogoutUserCommand) -> None:
        if not cmd.refresh_token:
            return
        token_hash = self.refresh_tokens.hash(cmd.refresh_token)

        async with self.uow_factory() as uow:
            session = await uow.refresh_sessions.get_by_token_hash_for_update(token_hash)
            if session is None or session.revoked_at is not None:
                return
            session.revoke()
            await uow.refresh_sessions.save(session)
            await uow.commit()
