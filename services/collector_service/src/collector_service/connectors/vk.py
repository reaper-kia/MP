"""ВКонтакте через VK API (сервисный ключ). Задача B1-03.

resolve  → groups.getById(group_id=<screen_name|id>, fields=city,members_count,is_closed)
collect  → wall.get(owner_id=-<id>, count=100, offset) пока посты новее period.start
           (закреплённый пост идёт первым и может быть старым — не останавливаться на нём)
search   → newsfeed.search(q, start_time, end_time, count=200, start_from) по каждой фразе
Соответствие полей VK → RawPost — в docs/tasks/B1-collector.md (B1-03).
"""

import httpx

from collector_service.config import Settings
from collector_service.connectors.base import NotImplementedConnector
from collector_service.models import Platform

VK_API = "https://api.vk.com/method/"


class VkConnector(NotImplementedConnector):
    platform = Platform.VK
    title = "ВКонтакте"
    hosts: tuple[str, ...] = ("vk.com", "vk.ru")
    task = "B1-03"

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._token = settings.vk_service_token
        self._version = settings.vk_api_version
        self._http = http

    # TODO(B1-03): health / resolve / collect / search
