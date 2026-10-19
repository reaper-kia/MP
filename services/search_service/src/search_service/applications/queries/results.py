from dataclasses import dataclass, field
from uuid import UUID

from search_service.applications.context import RequestContext
from search_service.applications.mediator import Command
from search_service.applications.results.read_models import ExportFile, GroupPage, ResultPage
from search_service.domain.enums import DateStatus, ExportFormat, Platform, Relevance, ResultSort


@dataclass(frozen=True)
class ResultFilter:
    """Пустые списки = «без ограничения», кроме relevance: пусто = DIRECT+INDIRECT+DISPUTED."""

    relevance: list[Relevance] = field(default_factory=list)
    platforms: list[Platform] = field(default_factory=list)
    target_ids: list[UUID] = field(default_factory=list)
    date_status: list[DateStatus] = field(default_factory=list)
    include_excluded: bool = False


@dataclass(frozen=True)
class ListResultsQuery(Command[ResultPage]):
    ctx: RequestContext
    search_id: UUID
    filter: ResultFilter = field(default_factory=ResultFilter)
    sort: ResultSort = ResultSort.RELEVANCE
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class ListGroupsQuery(Command[GroupPage]):
    ctx: RequestContext
    search_id: UUID
    filter: ResultFilter = field(default_factory=ResultFilter)
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class ExportSearchQuery(Command[ExportFile]):
    ctx: RequestContext
    search_id: UUID
    format: ExportFormat = ExportFormat.XLSX
    filter: ResultFilter = field(default_factory=ResultFilter)
    sort: ResultSort = ResultSort.RELEVANCE
