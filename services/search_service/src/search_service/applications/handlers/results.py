from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from search_service.applications.commands.results import SetExcludedCommand
from search_service.applications.exceptions import NotImplementedYetError
from search_service.applications.ports.unit_of_work import UnitOfWorkFactory
from search_service.applications.ports.uow import UnitOfWork
from search_service.applications.queries.results import ListGroupsQuery, ListResultsQuery
from search_service.applications.results.read_models import (
    GroupPage,
    ResultPage,
    SearchCountsView,
)
from search_service.domain.entities import SearchResult
from search_service.domain.enums import Relevance
from search_service.domain.errors import NotFoundError


@dataclass
class ResultFilter:
    relevance: list[str] | None = None
    platforms: list[str] | None = None
    target_ids: list[uuid.UUID] | None = None
    date_status: list[str] | None = None
    include_excluded: bool = False


class ResultsHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def list_results(
        self,
        search_id: uuid.UUID,
        f: ResultFilter,
        sort: str = "relevance",
        limit: int = 50,
        offset: int = 0,
        max_limit: int = 200,
    ) -> tuple[list[SearchResult], int, bool, dict[str, int]]:
        # max_limit: экран — до 200 на страницу, экспорт берёт всё (см. ExportHandler)
        limit = max(1, min(limit or 50, max_limit))
        async with self.uow:
            search = await self.uow.searches.get_by_id(search_id)
            if not search:
                raise NotFoundError("SEARCH_NOT_FOUND")
            rel = f.relevance or [Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED]
            results, total, has_more = await self.uow.results.list_filtered(
                search_id=search_id,
                relevance=rel,
                platforms=f.platforms,
                target_ids=f.target_ids,
                date_status=f.date_status,
                include_excluded=f.include_excluded,
                sort=sort,
                limit=limit,
                offset=offset,
            )
            counts = await self.uow.results.counts(search_id)
            return results, total, has_more, counts

    async def list_groups(
        self, search_id: uuid.UUID, f: ResultFilter, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int, bool]:
        """Группирует результаты по group_id, representative = первый по релевантности."""
        async with self.uow:
            search = await self.uow.searches.get_by_id(search_id)
            if not search:
                raise NotFoundError("SEARCH_NOT_FOUND")
            # получаем все результаты без limit
            results, _, _ = await self.uow.results.list_filtered(
                search_id=search_id,
                relevance=f.relevance or [Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED],
                platforms=f.platforms,
                target_ids=f.target_ids,
                date_status=f.date_status,
                include_excluded=f.include_excluded,
                sort="relevance",
                limit=10000,
                offset=0,
            )
            pub_ids = [r.publication_id for r in results]
            pubs = await self.uow.publications.get_by_ids(pub_ids)
            pubs_by_id = {p.id: p for p in pubs}

        # группировка
        groups: dict[str, list[SearchResult]] = {}
        for r in results:
            gid = r.group_id or str(r.id)
            groups.setdefault(gid, []).append(r)

        group_list: list[dict[str, Any]] = []
        for gid, items in groups.items():
            rep = items[0]
            pub = pubs_by_id.get(rep.publication_id)
            dates: list[datetime] = [
                d
                for r in items
                if r.publication_id in pubs_by_id
                and (d := pubs_by_id[r.publication_id].published_at) is not None
            ]
            group_list.append(
                {
                    "group_id": gid,
                    "title": pub.title if pub else "",
                    "size": len(items),
                    "platforms": list(
                        {
                            pubs_by_id[r.publication_id].platform
                            for r in items
                            if r.publication_id in pubs_by_id
                        }
                    ),
                    "earliest_published_at": min(dates, default=None),
                    "results": items,
                }
            )

        total = len(group_list)
        return group_list[offset : offset + limit], total, offset + limit < total


# ---------------------------------------------------------------------------
# Хэндлеры медиатора для gRPC-транспорта (каркас из main, регистрируются в
# dependencies.build_mediator). Пока не связаны с реализацией выше.
# ---------------------------------------------------------------------------


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
