from dataclasses import dataclass
from uuid import UUID

from auth_service.applications.context import RequestContext
from auth_service.applications.mediator import Command
from auth_service.applications.results.read_models import UserReadModel


@dataclass(frozen=True)
class GetUserQuery(Command[UserReadModel]):
    ctx: RequestContext
    user_id: UUID | None  # None — текущий пользователь
