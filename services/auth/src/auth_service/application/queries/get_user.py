from dataclasses import dataclass
from uuid import UUID

from auth_service.application.dto import UserView
from auth_service.application.ports import UnitOfWorkFactory
from auth_service.domain.errors import UserNotFoundError
from platform_common.context import RequestContext
from platform_common.mediator import Query


@dataclass(frozen=True, slots=True)
class GetUser(Query[UserView]):
    ctx: RequestContext
    user_id: UUID | None  # None — текущий пользователь


class GetUserHandler:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, query: GetUser) -> UserView:
        actor = query.ctx.require_user()
        user_id = query.user_id or actor
        async with self._uow_factory() as uow:
            user = await uow.users.get(user_id)
        if user is None:
            raise UserNotFoundError()
        # Чужой email видит только админ
        hide_email = user.id != actor and not query.ctx.is_admin
        return UserView.from_user(user, hide_email=hide_email)
