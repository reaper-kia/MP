from dataclasses import dataclass
from uuid import UUID

from search_service.applications.context import RequestContext
from search_service.applications.mediator import Command
from search_service.applications.results.read_models import SearchCountsView


@dataclass(frozen=True)
class SetExcludedCommand(Command[SearchCountsView]):
    ctx: RequestContext
    search_id: UUID
    result_ids: list[UUID]
    excluded: bool
