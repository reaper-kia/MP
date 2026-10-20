import ssl
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import certifi
import httpx

from collector_service.domain import messages
from collector_service.domain.exceptions import PlatformUnavailableError
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
        verify=tls_context(settings.http_ca_bundle),
    )


def tls_context(extra_ca_file: str) -> ssl.SSLContext:
    """certifi + системные корни + (если задан) свой PEM — например, УЦ Минцифры.

    Сертификаты части российских площадок выпущены УЦ, которого нет в certifi; без него
    httpx падает на CERTIFICATE_VERIFY_FAILED.
    """
    context = ssl.create_default_context(cafile=certifi.where())
    context.load_default_certs()
    if extra_ca_file:
        path = Path(extra_ca_file)
        if not path.is_file():
            raise RuntimeError(f"HTTP_CA_BUNDLE: файл не найден: {extra_ca_file}")
        context.load_verify_locations(cafile=str(path))
    return context


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


class HttpxJsonPoster:
    """JsonPoster (Yandex Search API) поверх общего httpx-клиента. Ключ — только в заголовке."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def post_json(
        self, url: str, body: Mapping[str, Any], headers: Mapping[str, str]
    ) -> tuple[int, Any]:
        try:
            response = await self._http.post(url, json=dict(body), headers=dict(headers))
        except httpx.HTTPError as exc:
            raise PlatformUnavailableError(
                messages.GLOBAL_SEARCH_DOWN,
                detail=f"Яндекс Поиск не отвечает ({type(exc).__name__})",
            ) from None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        return response.status_code, payload
