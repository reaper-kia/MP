from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from search_service.applications.commands.results import SetExcludedCommand
from search_service.applications.handlers.control import ControlHandler
from search_service.applications.handlers.errors import domain_errors
from search_service.applications.handlers.views import counts_view, result_view
from search_service.applications.ports.runner import SearchRunner
from search_service.applications.ports.uow import UnitOfWork
from search_service.applications.queries.results import ListGroupsQuery, ListResultsQuery
from search_service.applications.queries.results import ResultFilter as ResultFilterQuery
from search_service.applications.results.read_models import (
    GroupPage,
    ResultGroupView,
    ResultPage,
    ResultView,
    SearchCountsView,
)
from search_service.domain.entities import SearchResult, Source
from search_service.domain.enums import IN_SELECTION, Platform, Relevance
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
# Хэндлеры медиатора для gRPC-транспорта (регистрируются в dependencies.build_mediator):
# запрос → ResultsHandler / ControlHandler → read model.
# ---------------------------------------------------------------------------


def filter_from_query(f: ResultFilterQuery) -> ResultFilter:
    """Фильтр запроса (enum'ы, пусто = без ограничения) → фильтр ResultsHandler (строки / None)."""
    return ResultFilter(
        relevance=[r.value for r in f.relevance] or None,
        platforms=[p.value for p in f.platforms] or None,
        target_ids=list(f.target_ids) or None,
        date_status=[d.value for d in f.date_status] or None,
        include_excluded=f.include_excluded,
    )


async def result_views(
    uow: UnitOfWork, search_id: uuid.UUID, results: list[SearchResult]
) -> list[ResultView]:
    """Результаты + публикации + источник из каталога + размер сюжета."""
    async with uow:
        pubs = {
            p.id: p for p in await uow.publications.get_by_ids([r.publication_id for r in results])
        }
        group_sizes = Counter(
            r.group_id
            for r in await uow.results.get_by_search(search_id)
            if r.group_id and r.relevance in IN_SELECTION and not r.excluded
        )
        catalog: dict[tuple[str, str], Source | None] = {}
        for p in pubs.values():
            key = (p.platform, p.source_external_id)
            if key not in catalog:
                catalog[key] = await uow.sources.get_by_key(*key)
    views: list[ResultView] = []
    for r in results:
        pub = pubs.get(r.publication_id)
        if pub is None:
            continue
        size = group_sizes.get(r.group_id, 1) if r.group_id else 1
        views.append(result_view(r, pub, catalog.get((pub.platform, pub.source_external_id)), size))
    return views


@dataclass
class ListResultsQueryHandler:
    uow: UnitOfWork

    async def handle(self, query: ListResultsQuery) -> ResultPage:
        """Фильтр (пустой relevance = DIRECT+INDIRECT+DISPUTED; relevance IS NULL — никогда),
        сортировка (RELEVANCE: класс → score → дата NULLS LAST), total без limit."""
        with domain_errors():
            results, total, has_more, _ = await ResultsHandler(self.uow).list_results(
                query.search_id,
                filter_from_query(query.filter),
                sort=query.sort.value,
                limit=query.limit,
                offset=query.offset,
            )
        items = await result_views(self.uow, query.search_id, results)
        return ResultPage(items=items, total=total, has_more=has_more)


@dataclass
class ListGroupsQueryHandler:
    uow: UnitOfWork

    async def handle(self, query: ListGroupsQuery) -> GroupPage:
        """Группы по group_id с ПОЛНЫМ списком размещений; title — у representative."""
        with domain_errors():
            groups, total, has_more = await ResultsHandler(self.uow).list_groups(
                query.search_id,
                filter_from_query(query.filter),
                limit=query.limit,
                offset=query.offset,
            )
        items: list[ResultGroupView] = []
        for g in groups:
            views = await result_views(self.uow, query.search_id, g["results"])
            if not views:
                continue
            items.append(
                ResultGroupView(
                    group_id=str(g["group_id"]),
                    title=views[0].title,
                    size=len(views),
                    platforms=list(dict.fromkeys(Platform(v.platform) for v in views)),
                    earliest_published_at=g["earliest_published_at"],
                    results=views,
                )
            )
        return GroupPage(items=items, total=total, has_more=has_more)


@dataclass
class SetExcludedCommandHandler:
    uow: UnitOfWork
    runner: SearchRunner

    async def handle(self, cmd: SetExcludedCommand) -> SearchCountsView:
        """Пачкой; чужой/несуществующий id → ResultNotFoundError; вернуть пересчитанные counts."""
        with domain_errors():
            counts = await ControlHandler(self.uow, self.runner).set_excluded(
                cmd.search_id, list(cmd.result_ids), cmd.excluded
            )
        return counts_view(counts)
