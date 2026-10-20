"""Работа с площадкой целиком: список площадок и поиск по всей площадке."""

import asyncio
from dataclasses import dataclass

from collector_service.applications.exceptions import InvalidRequestError
from collector_service.applications.handlers.common import check_period, collect_pages
from collector_service.applications.limits import CollectLimits
from collector_service.applications.ports.connectors import ConnectorRegistry, PlatformConnector
from collector_service.applications.queries.platforms import GetPlatformsQuery, SearchPlatformQuery
from collector_service.domain.enums import Health
from collector_service.domain.value_objects import CollectResult, PlatformInfo

# gateway ждёт GetPlatforms 5 с: каждой площадке — не больше 3.5 с, иначе отменится весь ответ
HEALTH_WAIT_SECONDS = 3.5
CHECKING_NOTE = "Проверка площадки ещё идёт — обновите страницу через минуту"


@dataclass
class GetPlatformsQueryHandler:
    registry: ConnectorRegistry
    wait_seconds: float = HEALTH_WAIT_SECONDS

    async def handle(self, query: GetPlatformsQuery) -> list[PlatformInfo]:
        # проверки площадок независимы — параллельно; у каждой свой кэш (5 мин / 1 мин)
        return list(await asyncio.gather(*(self._health(c) for c in self.registry.all())))

    async def _health(self, connector: PlatformConnector) -> PlatformInfo:
        # shield: долгая проверка не отменяется вместе с ответом, а доживает и кладёт итог
        # в кэш коннектора — следующий GetPlatforms отдаст его сразу
        check = asyncio.ensure_future(connector.health())
        try:
            return await asyncio.wait_for(asyncio.shield(check), self.wait_seconds)
        except TimeoutError:
            return PlatformInfo(
                platform=connector.platform,
                title=connector.title,
                source_mode_supported=True,
                global_mode_supported=False,
                health=Health.DEGRADED,
                note=CHECKING_NOTE,
            )


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
