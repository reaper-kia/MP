from dataclasses import dataclass, field

from search_service.applications.context import RequestContext
from search_service.applications.mediator import Command
from search_service.applications.results.read_models import SourcePage, SourcePreviewView
from search_service.domain.enums import Platform


@dataclass(frozen=True)
class ResolveSourceQuery(Command[SourcePreviewView]):
    ctx: RequestContext
    url: str


@dataclass(frozen=True)
class ListSourcesQuery(Command[SourcePage]):
    ctx: RequestContext
    platforms: list[Platform] = field(default_factory=list)  # пусто — все
    q: str = ""
    is_active: bool | None = None
    limit: int = 50
    offset: int = 0
