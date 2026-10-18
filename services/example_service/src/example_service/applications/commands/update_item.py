from dataclasses import dataclass
from uuid import UUID

from example_service.applications.context import RequestContext
from example_service.applications.mediator import Command
from example_service.applications.results.read_models import ItemReadModel


@dataclass(frozen=True)
class UpdateItemCommand(Command[ItemReadModel]):
    ctx: RequestContext
    item_id: UUID
    # None — не менять
    title: str | None = None
    description: str | None = None
    status: str | None = None
