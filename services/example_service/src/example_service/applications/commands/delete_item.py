from dataclasses import dataclass
from uuid import UUID

from example_service.applications.context import RequestContext
from example_service.applications.mediator import Command


@dataclass(frozen=True)
class DeleteItemCommand(Command[None]):
    ctx: RequestContext
    item_id: UUID
