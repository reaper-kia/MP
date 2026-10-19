"""Новостные сайты из перечня агентства (RSS / sitemap). Задача B1-08 (P1)."""

import httpx

from collector_service.config import Settings
from collector_service.connectors.base import NotImplementedConnector
from collector_service.models import Platform


class NewsConnector(NotImplementedConnector):
    platform = Platform.NEWS
    title = "Новостные сайты"
    # Хосты сайтов из стартовых материалов кейса — дописать сюда
    hosts: tuple[str, ...] = ()
    task = "B1-08"

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http
