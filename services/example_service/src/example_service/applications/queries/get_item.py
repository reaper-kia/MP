from dataclasses import dataclass
from uuid import UUID

from example_service.applications.context import RequestContext
from example_service.applications.mediator import Command
from example_service.applications.results.read_models import ItemReadModel


@dataclass(frozen=True)
class GetItemQuery(Command[ItemReadModel]):
    ctx: RequestContext
    item_id: UUID
