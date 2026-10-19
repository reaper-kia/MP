"""Поисковые задачи. Задачи B2-03 (старт, чтение), B2-04 (пайплайн), B2-09 (повтор, отмена)."""

from dataclasses import dataclass

from search_service.applications.commands.searches import (
    CancelSearchCommand,
    RetrySearchCommand,
    StartSearchCommand,
)
from search_service.applications.exceptions import NotImplementedYetError
from search_service.applications.ports.collector import CollectorClient
from search_service.applications.ports.ml import MlClient
from search_service.applications.ports.unit_of_work import UnitOfWorkFactory
from search_service.applications.queries.searches import GetSearchQuery, ListSearchesQuery
from search_service.applications.results.read_models import SearchPage, SearchView


@dataclass
class StartSearchCommandHandler:
    uow_factory: UnitOfWorkFactory
    collector: CollectorClient
    ml: MlClient

    async def handle(self, cmd: StartSearchCommand) -> SearchView:
        """1) валидация → SearchInvalidParamsError("<поле>: <текст>"); период —
        UtcPeriod.from_local_dates; 2) Search + цели (снимок name/url) в одной транзакции;
        3) запустить пайплайн фоновой задачей (B2-04) и сразу вернуть status=QUEUED."""
        raise NotImplementedYetError("StartSearch: B2-03")


@dataclass
class GetSearchQueryHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, query: GetSearchQuery) -> SearchView:
        """Поиск + цели + счётчики (одним SQL по search_results) + прогресс."""
        raise NotImplementedYetError("GetSearch: B2-03")


@dataclass
class ListSearchesQueryHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, query: ListSearchesQuery) -> SearchPage:
        """Новые сверху, без targets; limit+1 для has_more (как в шаблоне)."""
        raise NotImplementedYetError("ListSearches: B2-03")


@dataclass
class RetrySearchCommandHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, cmd: RetrySearchCommand) -> SearchView:
        """Только FAILED цели (или указанные); поиск ещё идёт → SearchNotFinishedError."""
        raise NotImplementedYetError("RetrySearch: B2-09")


@dataclass
class CancelSearchCommandHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, cmd: CancelSearchCommand) -> SearchView:
        """Отменить фоновую задачу; незавершённые цели → SKIPPED; статус CANCELLED."""
        raise NotImplementedYetError("CancelSearch: B2-09")
