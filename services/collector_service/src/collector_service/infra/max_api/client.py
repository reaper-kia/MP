"""Вызов MAX Bot API. Знает про сеть и коды ответа, но не про посты.

Документация: https://dev.max.ru/docs-api. Токен бота — в заголовке `Authorization` (без
«Bearer»), в URL и логи не попадает. Для TLS к platform-api нужен корневой сертификат
Минцифры — его путь задаётся HTTP_CA_BUNDLE (infra/http.py).
"""

from collections.abc import Mapping
from typing import Any

import httpx

from collector_service.domain import messages
from collector_service.domain.exceptions import (
    PlatformUnavailableError,
    RateLimitedError,
    SourceNotFoundError,
    SourcePrivateError,
)
from collector_service.infra.vk_api.limiter import RateLimiter

DEFAULT_API_URL = "https://platform-api2.max.ru"


class MaxApiClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        token: str,
        base_url: str = DEFAULT_API_URL,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._http = http
        self._token = token
        self._base = base_url.rstrip("/")
        self._limiter = limiter or RateLimiter(5.0)

    @property
    def configured(self) -> bool:
        return bool(self._token)

    async def get(self, path: str, **params: str | int) -> Any:
        if not self.configured:
            raise PlatformUnavailableError(
                messages.not_configured("MAX"), detail="MAX: не задан MAX_BOT_TOKEN"
            )
        await self._limiter.wait()
        try:
            response = await self._http.get(
                self._base + path,
                params={k: str(v) for k, v in params.items()},
                headers={"Authorization": self._token},
            )
        except httpx.HTTPError as exc:
            raise PlatformUnavailableError(
                messages.no_answer("MAX"), detail=f"MAX {path}: сеть: {type(exc).__name__}"
            ) from None
        return _payload(response)


def _payload(response: httpx.Response) -> Any:
    status = response.status_code
    detail = f"MAX: HTTP {status}"
    if status == 401:
        raise PlatformUnavailableError(messages.access_denied("MAX"), detail=detail)
    if status == 403:
        raise SourcePrivateError(
            "MAX: нет доступа к каналу — добавьте бота сервиса администратором канала",
            detail=detail,
        )
    if status == 404:
        raise SourceNotFoundError(messages.source_not_found("MAX"), detail=detail)
    if status == 429:
        raise RateLimitedError(messages.too_many_requests("MAX"), detail=detail)
    if status >= 500:
        raise PlatformUnavailableError(messages.no_answer("MAX"), detail=detail)
    if status >= 400:
        raise PlatformUnavailableError(messages.bad_answer("MAX"), detail=detail)
    try:
        data = response.json()
    except ValueError:
        raise PlatformUnavailableError(
            messages.bad_answer("MAX"), detail=f"{detail}, ответ не JSON"
        ) from None
    return data if isinstance(data, Mapping) else {}
