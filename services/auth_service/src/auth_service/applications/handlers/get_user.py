from dataclasses import dataclass

from auth_service.applications.exceptions import UserNotFoundError
from auth_service.applications.ports.unit_of_work import UnitOfWorkFactory
from auth_service.applications.queries.get_user import GetUserQuery
from auth_service.applications.results.read_models import UserReadModel


@dataclass
class GetUserQueryHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, query: GetUserQuery) -> UserReadModel:
        actor_id = query.ctx.require_user()
        user_id = query.user_id or actor_id

        async with self.uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)

        if user is None:
            raise UserNotFoundError("User not found")

        # чужой email видит только админ
        hide_email = user.id != actor_id and not query.ctx.is_admin
        return UserReadModel.from_user(user, hide_email=hide_email)
