from dataclasses import dataclass

from example_service.applications.context import RequestContext
from example_service.applications.mediator import Command
from example_service.applications.results.read_models import ItemReadModel


@dataclass(frozen=True)
class CreateItemCommand(Command[ItemReadModel]):
    ctx: RequestContext
    title: str
    description: str = ""
