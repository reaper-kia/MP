"""Работа с площадкой целиком: список площадок и поиск по всей площадке."""

from dataclasses import dataclass

from collector_service.applications.exceptions import InvalidRequestError
from collector_service.applications.handlers.common import check_period, log_finalized
from collector_service.applications.limits import CollectLimits
from collector_service.applications.ports.connectors import ConnectorRegistry
from collector_service.applications.queries.platforms import GetPlatformsQuery, SearchPlatformQuery
from collector_service.domain.services import finalize_result
from collector_service.domain.value_objects import CollectResult, PlatformInfo


@dataclass
class GetPlatformsQueryHandler:
    registry: ConnectorRegistry

    async def handle(self, query: GetPlatformsQuery) -> list[PlatformInfo]:
        return [await connector.health() for connector in self.registry.all()]


@dataclass
class SearchPlatformQueryHandler:
    registry: ConnectorRegistry
    limits: CollectLimits

    async def handle(self, query: SearchPlatformQuery) -> CollectResult:
        cleaned = [q.strip() for q in query.queries if q.strip()]
        if not cleaned:
            raise InvalidRequestError("Нужна хотя бы одна поисковая фраза")
        check_period(query.period)
        limit = query.max_posts or self.limits.per_search
        connector = self.registry.get(query.platform)
        result = await connector.search(cleaned, query.period, query.region_terms, limit)
        finalized, stats = finalize_result(result, query.period, limit)
        log_finalized(query.ctx, f"{query.platform}:search", stats, finalized.truncated)
        return finalized
