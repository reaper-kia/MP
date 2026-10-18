from dataclasses import dataclass

from auth_service.application.ports import TokenService, UnitOfWorkFactory
from platform_common.context import RequestContext
from platform_common.mediator import Command


@dataclass(frozen=True, slots=True)
class LogoutUser(Command[None]):
    ctx: RequestContext
    refresh_token: str


class LogoutUserHandler:
    """Идемпотентно: неизвестный/уже отозванный токен — не ошибка."""

    def __init__(self, uow_factory: UnitOfWorkFactory, tokens: TokenService) -> None:
        self._uow_factory = uow_factory
        self._tokens = tokens

    async def handle(self, cmd: LogoutUser) -> None:
        if not cmd.refresh_token:
            return
        async with self._uow_factory() as uow:
            session = await uow.sessions.get_by_token_hash(
                self._tokens.hash_refresh_token(cmd.refresh_token)
            )
            if session is None or session.revoked_at is not None:
                return
            session.revoke()
            await uow.sessions.update(session)
            await uow.commit()
