"""Одноклассники. Способ получения — по итогам spike B1-01 (docs/collector-spike.md). Задача B1-04.

Каноничная ссылка на пост: https://ok.ru/group/{gid}/topic/{topic_id}
"""

import httpx

from collector_service.domain.enums import Platform
from collector_service.infra.config import Settings
from collector_service.infra.connectors.base import NotImplementedConnector


class OkConnector(NotImplementedConnector):
    platform = Platform.OK
    title = "Одноклассники"
    hosts: tuple[str, ...] = ("ok.ru",)
    task = "B1-04"

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http

    # TODO(B1-04): health / resolve / collect; search — через Yandex Search API (B1-06)
