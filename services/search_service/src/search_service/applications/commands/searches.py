from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from search_service.applications.context import RequestContext
from search_service.applications.mediator import Command
from search_service.applications.results.read_models import SearchView
from search_service.domain.enums import Platform, SearchMode


@dataclass(frozen=True)
class StartSearchCommand(Command[SearchView]):
    ctx: RequestContext
    query: str
    period_from: date
    period_to: date
    mode: SearchMode
    platforms: list[Platform]
    source_ids: list[UUID] = field(default_factory=list)
    fresh: bool = False  # true — мимо кэша готовых подборок («Обновить»), B2-20


@dataclass(frozen=True)
class RetrySearchCommand(Command[SearchView]):
    ctx: RequestContext
    search_id: UUID
    target_ids: list[UUID] = field(default_factory=list)  # пусто — все FAILED


@dataclass(frozen=True)
class CancelSearchCommand(Command[SearchView]):
    ctx: RequestContext
    search_id: UUID
