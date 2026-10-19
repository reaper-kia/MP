from __future__ import annotations
import uuid
from dataclasses import dataclass

from search_service.domain.enums import Relevance
from search_service.domain.errors import NotFoundError
from search_service.applications.ports.uow import UnitOfWork


@dataclass
class ResultFilter:
    relevance: list[str] | None = None
    platforms: list[str] | None = None
    target_ids: list[uuid.UUID] | None = None
    date_status: list[str] | None = None
    include_excluded: bool = False


class ResultsHandler:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def list_results(self, search_id: uuid.UUID, f: ResultFilter,
                           sort: str = "relevance", limit: int = 50, offset: int = 0):
        limit = max(1, min(limit or 50, 200))
        async with self.uow:
            search = await self.uow.searches.get(search_id)
            if not search:
                raise NotFoundError("SEARCH_NOT_FOUND")
            rel = f.relevance or [Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED]
            results, total, has_more = await self.uow.results.list_filtered(
                search_id=search_id, relevance=rel, platforms=f.platforms,
                target_ids=f.target_ids, date_status=f.date_status,
                include_excluded=f.include_excluded, sort=sort,
                limit=limit, offset=offset,
            )
            counts = await self.uow.results.counts(search_id)
            return results, total, has_more, counts

    async def list_groups(self, search_id: uuid.UUID, f: ResultFilter,
                          limit: int = 50, offset: int = 0):
        """Группирует результаты по group_id, representative = первый по релевантности."""
        async with self.uow:
            search = await self.uow.searches.get(search_id)
            if not search:
                raise NotFoundError("SEARCH_NOT_FOUND")
            # получаем все результаты без limit
            results, _, _ = await self.uow.results.list_filtered(
                search_id=search_id, relevance=f.relevance or [
                    Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED
                ], platforms=f.platforms, target_ids=f.target_ids,
                date_status=f.date_status, include_excluded=f.include_excluded,
                sort="relevance", limit=10000, offset=0,
            )
            pub_ids = [r.publication_id for r in results]
            pubs = await self.uow.publications.get_by_ids(pub_ids)
            pubs_by_id = {p.id: p for p in pubs}

        # группировка
        groups: dict[str, list] = {}
        for r in results:
            gid = r.group_id or str(r.id)
            groups.setdefault(gid, []).append(r)

        group_list = []
        for gid, items in groups.items():
            rep = items[0]
            pub = pubs_by_id.get(rep.publication_id)
            group_list.append({
                "group_id": gid,
                "title": pub.title if pub else "",
                "size": len(items),
                "platforms": list({pubs_by_id[r.publication_id].platform for r in items
                                    if r.publication_id in pubs_by_id}),
                "earliest_published_at": min(
                    (pubs_by_id[r.publication_id].published_at
                     for r in items if r.publication_id in pubs_by_id
                     and pubs_by_id[r.publication_id].published_at),
                    default=None,
                ),
                "results": items,
            })

        total = len(group_list)
        return group_list[offset:offset + limit], total, offset + limit < total