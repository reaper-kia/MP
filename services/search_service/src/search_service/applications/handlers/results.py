"""Подборка. Задачи B2-07 (выдача, группы, счётчики), B2-09 (исключение)."""

from dataclasses import dataclass

from search_service.applications.commands.results import SetExcludedCommand
from search_service.applications.exceptions import NotImplementedYetError
from search_service.applications.ports.unit_of_work import UnitOfWorkFactory
from search_service.applications.queries.results import ListGroupsQuery, ListResultsQuery
from search_service.applications.results.read_models import (
    GroupPage,
    ResultPage,
    SearchCountsView,
)


@dataclass
class ListResultsQueryHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, query: ListResultsQuery) -> ResultPage:
        """Фильтр (пустой relevance = DIRECT+INDIRECT+DISPUTED; relevance IS NULL — никогда),
        сортировка (RELEVANCE: класс → score → дата NULLS LAST), total без limit."""
        raise NotImplementedYetError("ListResults: B2-07")


@dataclass
class ListGroupsQueryHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, query: ListGroupsQuery) -> GroupPage:
        """Группы по group_id с ПОЛНЫМ списком размещений; title — у representative."""
        raise NotImplementedYetError("ListGroups: B2-07")


@dataclass
class SetExcludedCommandHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, cmd: SetExcludedCommand) -> SearchCountsView:
        """Пачкой; чужой/несуществующий id → ResultNotFoundError; вернуть пересчитанные counts."""
        raise NotImplementedYetError("SetExcluded: B2-09")
