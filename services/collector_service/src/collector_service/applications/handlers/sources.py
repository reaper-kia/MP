"""Работа с конкретным источником: карточка по ссылке и посты источника за период."""

from dataclasses import dataclass

from collector_service.applications.exceptions import InvalidRequestError
from collector_service.applications.handlers.common import check_period, collect_pages
from collector_service.applications.limits import CollectLimits
from collector_service.applications.ports.connectors import ConnectorRegistry
from collector_service.applications.queries.sources import (
    CollectFromSourceQuery,
    ResolveSourceQuery,
)
from collector_service.domain.urls import normalize_url
from collector_service.domain.value_objects import CollectResult, SourceInfo


@dataclass
class ResolveSourceQueryHandler:
    """Кэш на 10 минут — CachingBehavior (ResolveSourceQuery.cache_key), не здесь."""

    registry: ConnectorRegistry

    async def handle(self, query: ResolveSourceQuery) -> SourceInfo:
        normalized = normalize_url(query.url)
        connector = self.registry.detect(normalized)
        return await connector.resolve(normalized)


@dataclass
class CollectFromSourceQueryHandler:
    registry: ConnectorRegistry
    limits: CollectLimits

    async def handle(self, query: CollectFromSourceQuery) -> CollectResult:
        if not query.source_external_id:
            raise InvalidRequestError("source_external_id обязателен")
        check_period(query.period)
        connector = self.registry.get(query.platform)
        return await collect_pages(
            query.ctx,
            f"{query.platform}:{query.source_external_id}",
            connector.collect(query.source_external_id, query.period, query.keywords),
            query.period,
            query.max_posts or self.limits.per_source,
            self.limits.budget_seconds,
        )
