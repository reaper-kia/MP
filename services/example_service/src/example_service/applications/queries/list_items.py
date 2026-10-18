from dataclasses import dataclass

from example_service.applications.context import RequestContext
from example_service.applications.mediator import Command
from example_service.applications.results.read_models import ItemPage


@dataclass(frozen=True)
class ListItemsQuery(Command[ItemPage]):
    ctx: RequestContext
    limit: int = 20
    offset: int = 0
