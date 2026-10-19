"""MAX. Способ получения — по итогам spike B1-01 (docs/collector-spike.md). Задача B1-05.

Известно: max.ru/<handle>/__data.json отдаёт метаданные канала, лимит по IP, формат менялся.
"""

import httpx

from collector_service.domain.enums import Platform
from collector_service.infra.config import Settings
from collector_service.infra.connectors.base import NotImplementedConnector


class MaxConnector(NotImplementedConnector):
    platform = Platform.MAX
    title = "MAX"
    hosts: tuple[str, ...] = ("max.ru",)
    task = "B1-05"

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http

    # TODO(B1-05): health / resolve / collect; search — если spike найдёт способ (B1-06)
