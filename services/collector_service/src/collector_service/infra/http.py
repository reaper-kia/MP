from collections.abc import Mapping
from typing import Any

import httpx

from collector_service.infra.config import Settings
from collector_service.infra.vk_api.transport import TransportError


def create_http_client(settings: Settings) -> httpx.AsyncClient:
    """Один клиент на сервис: пул соединений, таймауты, User-Agent.

    Закрывается в Container.close().
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        headers={"User-Agent": settings.http_user_agent},
        follow_redirects=True,
    )


class HttpxFormPoster:
    """FormPoster поверх общего httpx-клиента. В текст ошибки не попадают URL и тело запроса."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def post_form(self, url: str, data: Mapping[str, str]) -> Any:
        try:
            response = await self._http.post(url, data=dict(data))
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TransportError(type(exc).__name__) from None
