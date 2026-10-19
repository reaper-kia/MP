from dataclasses import dataclass
from uuid import UUID

from search_service.applications.context import RequestContext
from search_service.applications.mediator import Command
from search_service.applications.results.read_models import SearchPage, SearchView


@dataclass(frozen=True)
class GetSearchQuery(Command[SearchView]):
    ctx: RequestContext
    search_id: UUID


@dataclass(frozen=True)
class ListSearchesQuery(Command[SearchPage]):
    ctx: RequestContext
    limit: int = 20
    offset: int = 0
