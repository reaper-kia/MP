"""Composition root: настройки → коннекторы → сервис."""

from dataclasses import dataclass

import httpx

from collector_service.config import Settings
from collector_service.connectors.base import PlatformConnector
from collector_service.connectors.fake import FakeConnector
from collector_service.connectors.max import MaxConnector
from collector_service.connectors.news import NewsConnector
from collector_service.connectors.ok import OkConnector
from collector_service.connectors.registry import ConnectorRegistry
from collector_service.connectors.vk import VkConnector
from collector_service.http import create_http_client
from collector_service.models import Platform
from collector_service.service import CollectorService


@dataclass(frozen=True)
class Container:
    http: httpx.AsyncClient
    service: CollectorService

    async def close(self) -> None:
        await self.http.aclose()


def build_connectors(settings: Settings, http: httpx.AsyncClient) -> list[PlatformConnector]:
    if settings.collector_fake:
        return [FakeConnector(p) for p in Platform]
    return [
        VkConnector(settings, http),
        OkConnector(settings, http),
        MaxConnector(settings, http),
        NewsConnector(settings, http),
    ]


def build_container(settings: Settings) -> Container:
    http = create_http_client(settings)
    registry = ConnectorRegistry(build_connectors(settings, http))
    return Container(http=http, service=CollectorService(registry, settings))
