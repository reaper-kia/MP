"""Минимальный порт «отправить форму, получить JSON».

Клиент VK зависит от него, а не от httpx: тесты подставляют заготовленные ответы без сети,
реализация на httpx — infra/http.py.
"""

from collections.abc import Mapping
from typing import Any, Protocol


class TransportError(Exception):
    """Сеть, таймаут, HTTP-статус не 2xx или тело не JSON. Текст — без параметров запроса."""


class FormPoster(Protocol):
    async def post_form(self, url: str, data: Mapping[str, str]) -> Any:
        """POST application/x-www-form-urlencoded → разобранный JSON. Ошибки — TransportError."""
        ...
