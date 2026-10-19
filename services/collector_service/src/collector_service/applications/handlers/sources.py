"""Работа с конкретным источником: карточка по ссылке и посты источника за период."""

from dataclasses import dataclass

from collector_service.applications.exceptions import InvalidRequestError
from collector_service.applications.handlers.common import check_period, log_finalized
from collector_service.applications.limits import CollectLimits
from collector_service.applications.ports.connectors import ConnectorRegistry
from collector_service.applications.queries.sources import (
    CollectFromSourceQuery,
    ResolveSourceQuery,
)
from collector_service.domain.services import finalize_result
from collector_service.domain.urls import normalize_url
from collector_service.domain.value_objects import CollectResult, SourceInfo


@dataclass
class ResolveSourceQueryHandler:
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
        limit = query.max_posts or self.limits.per_source
        connector = self.registry.get(query.platform)
        result = await connector.collect(
            query.source_external_id, query.period, query.keywords, limit
        )
        finalized, stats = finalize_result(result, query.period, limit)
        where = f"{query.platform}:{query.source_external_id}"
        log_finalized(query.ctx, where, stats, finalized.truncated)
        return finalized
