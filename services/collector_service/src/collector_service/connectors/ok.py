"""Одноклассники. Способ получения — по итогам spike B1-01 (docs/collector-spike.md). Задача B1-04.

Каноничная ссылка на пост: https://ok.ru/group/{gid}/topic/{topic_id}
"""

import httpx

from collector_service.config import Settings
from collector_service.connectors.base import NotImplementedConnector
from collector_service.models import Platform


class OkConnector(NotImplementedConnector):
    platform = Platform.OK
    title = "Одноклассники"
    hosts: tuple[str, ...] = ("ok.ru",)
    task = "B1-04"

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http

    # TODO(B1-04): health / resolve / collect; search — через Yandex Search API (B1-06)
