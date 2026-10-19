"""Новостные сайты из перечня агентства (RSS / sitemap). Задача B1-08 (P1)."""

import httpx

from collector_service.domain.enums import Platform
from collector_service.infra.config import Settings
from collector_service.infra.connectors.base import NotImplementedConnector


class NewsConnector(NotImplementedConnector):
    platform = Platform.NEWS
    title = "Новостные сайты"
    # Хосты сайтов из стартовых материалов кейса — дописать сюда
    hosts: tuple[str, ...] = ()
    task = "B1-08"

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http
