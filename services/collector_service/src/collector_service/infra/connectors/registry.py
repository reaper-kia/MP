from collections.abc import Iterable

from collector_service.applications.exceptions import InvalidRequestError
from collector_service.applications.ports.connectors import PlatformConnector
from collector_service.domain.enums import Platform
from collector_service.domain.exceptions import UnsupportedUrlError
from collector_service.domain.urls import host_of


class InMemoryConnectorRegistry:
    def __init__(self, connectors: Iterable[PlatformConnector]) -> None:
        self._by_platform: dict[Platform, PlatformConnector] = {}
        for connector in connectors:
            if connector.platform in self._by_platform:
                raise ValueError(f"Duplicate connector for {connector.platform}")
            self._by_platform[connector.platform] = connector

    def get(self, platform: Platform) -> PlatformConnector:
        connector = self._by_platform.get(platform)
        if connector is None:
            raise InvalidRequestError(f"Площадка {platform} не поддерживается")
        return connector

    def all(self) -> list[PlatformConnector]:
        return list(self._by_platform.values())

    def detect(self, url: str) -> PlatformConnector:
        """Какая площадка у ссылки — по хосту."""
        host = host_of(url)
        for connector in self._by_platform.values():
            if any(host == h or host.endswith("." + h) for h in connector.hosts):
                return connector
        raise UnsupportedUrlError("Это не похоже на ссылку на группу VK, OK или канал MAX")
