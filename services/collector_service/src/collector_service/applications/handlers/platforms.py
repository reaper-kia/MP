"""Работа с площадкой целиком: список площадок и поиск по всей площадке."""

import asyncio
from dataclasses import dataclass

from collector_service.applications.exceptions import InvalidRequestError
from collector_service.applications.handlers.common import check_period, collect_pages
from collector_service.applications.limits import CollectLimits
from collector_service.applications.ports.connectors import ConnectorRegistry
from collector_service.applications.queries.platforms import GetPlatformsQuery, SearchPlatformQuery
from collector_service.domain.value_objects import CollectResult, PlatformInfo


@dataclass
class GetPlatformsQueryHandler:
    registry: ConnectorRegistry

    async def handle(self, query: GetPlatformsQuery) -> list[PlatformInfo]:
        # проверки площадок независимы — параллельно; у каждой свой кэш (5 мин / 1 мин)
        return list(await asyncio.gather(*(c.health() for c in self.registry.all())))


@dataclass
class SearchPlatformQueryHandler:
    registry: ConnectorRegistry
    limits: CollectLimits

    async def handle(self, query: SearchPlatformQuery) -> CollectResult:
        cleaned = [q.strip() for q in query.queries if q.strip()]
        if not cleaned:
            raise InvalidRequestError("Нужна хотя бы одна поисковая фраза")
        check_period(query.period)
        connector = self.registry.get(query.platform)
        return await collect_pages(
            query.ctx,
            f"{query.platform}:search",
            connector.search(cleaned, query.period, query.region_terms),
            query.period,
            query.max_posts or self.limits.per_search,
            self.limits.budget_seconds,
        )
