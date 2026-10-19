"""Composition root: настройки → коннекторы → реестр → хэндлеры в Mediator."""

from dataclasses import dataclass

import httpx

from collector_service.applications.handlers.platforms import (
    GetPlatformsQueryHandler,
    SearchPlatformQueryHandler,
)
from collector_service.applications.handlers.sources import (
    CollectFromSourceQueryHandler,
    ResolveSourceQueryHandler,
)
from collector_service.applications.limits import CollectLimits
from collector_service.applications.mediator import Mediator
from collector_service.applications.ports.connectors import ConnectorRegistry, PlatformConnector
from collector_service.applications.queries.platforms import GetPlatformsQuery, SearchPlatformQuery
from collector_service.applications.queries.sources import (
    CollectFromSourceQuery,
    ResolveSourceQuery,
)
from collector_service.domain.enums import Platform
from collector_service.infra.config import Settings
from collector_service.infra.connectors.fake import FakeConnector
from collector_service.infra.connectors.max import MaxConnector
from collector_service.infra.connectors.news import NewsConnector
from collector_service.infra.connectors.ok import OkConnector
from collector_service.infra.connectors.registry import InMemoryConnectorRegistry
from collector_service.infra.connectors.vk import VkConnector
from collector_service.infra.http import HttpxFormPoster, create_http_client
from collector_service.infra.vk_api.client import VkApiClient
from collector_service.infra.vk_api.limiter import RateLimiter


@dataclass(frozen=True)
class Container:
    http: httpx.AsyncClient
    mediator: Mediator

    async def close(self) -> None:
        await self.http.aclose()


def build_vk(settings: Settings, http: httpx.AsyncClient) -> VkConnector:
    client = VkApiClient(
        HttpxFormPoster(http),
        token=settings.vk_service_token,
        version=settings.vk_api_version,
        limiter=RateLimiter(settings.vk_requests_per_second),
    )
    return VkConnector(client)


def build_connectors(settings: Settings, http: httpx.AsyncClient) -> list[PlatformConnector]:
    if settings.collector_fake:
        return [FakeConnector(p) for p in Platform]
    return [
        build_vk(settings, http),
        OkConnector(settings, http),
        MaxConnector(settings, http),
        NewsConnector(settings, http),
    ]


def build_mediator(registry: ConnectorRegistry, limits: CollectLimits) -> Mediator:
    mediator = Mediator()
    mediator.register(GetPlatformsQuery, GetPlatformsQueryHandler(registry))
    mediator.register(ResolveSourceQuery, ResolveSourceQueryHandler(registry))
    mediator.register(CollectFromSourceQuery, CollectFromSourceQueryHandler(registry, limits))
    mediator.register(SearchPlatformQuery, SearchPlatformQueryHandler(registry, limits))
    return mediator


def build_container(settings: Settings) -> Container:
    http = create_http_client(settings)
    registry = InMemoryConnectorRegistry(build_connectors(settings, http))
    limits = CollectLimits(
        per_source=settings.default_max_posts_source,
        per_search=settings.default_max_posts_search,
    )
    return Container(http=http, mediator=build_mediator(registry, limits))
