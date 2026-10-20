"""GET публичной страницы: лимит запросов на хост, повтор при сбое сети, понятные ошибки.

Коннекторы OK / MAX / сайтов зависят от порта WebFetcher, а не от httpx: тесты подставляют
сохранённые страницы (tests/fixtures/<площадка>/) без сети.

Ошибки → domain/exceptions.py:
  404 / 410                      → SourceNotFoundError
  429                            → RateLimitedError (просит подождать; ротацию IP не делаем)
  403, капча, «подтвердите, что вы не робот» → PlatformUnavailableError «анти-бот»
  5xx, сеть, таймаут (после повтора) → PlatformUnavailableError
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from collector_service.domain import messages
from collector_service.domain.exceptions import (
    PlatformUnavailableError,
    RateLimitedError,
    SourceNotFoundError,
)
from collector_service.infra.vk_api.limiter import RateLimiter

logger = logging.getLogger(__name__)

ANTIBOT_MARKERS = (
    "captcha",
    "капча",
    "подтвердите, что вы не робот",
    "докажите, что вы не робот",
    "доступ ограничен",
)
# Анти-бот ищем только в начале коротких страниц: в длинной ленте слово «капча» может
# встретиться в тексте поста
ANTIBOT_SCAN_LIMIT = 20_000


@dataclass(frozen=True, slots=True)
class WebPage:
    url: str  # итоговый адрес после редиректов
    status: int
    text: str
    content_type: str = ""
    headers: Mapping[str, str] = field(default_factory=dict)


class WebFetcher(Protocol):
    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        what: str = "",
    ) -> WebPage:
        """Страница целиком (только 2xx). `what` — как назвать площадку в тексте ошибки."""
        ...

    async def post(
        self,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        what: str = "",
    ) -> WebPage:
        """POST формы (подгрузка следующей страницы ленты). Ошибки — как у get."""
        ...


class HostLimiters:
    """Свой RateLimiter на каждый хост (B1-09 п. 3): OK и MAX не мешают друг другу."""

    def __init__(self, per_second: float, overrides: Mapping[str, float] | None = None) -> None:
        self._default = per_second
        self._overrides = dict(overrides or {})
        self._limiters: dict[str, RateLimiter] = {}

    def for_host(self, host: str) -> RateLimiter:
        limiter = self._limiters.get(host)
        if limiter is None:
            rate = next(
                (r for h, r in self._overrides.items() if host == h or host.endswith("." + h)),
                self._default,
            )
            limiter = self._limiters[host] = RateLimiter(rate)
        return limiter


class HttpxWebFetcher:
    def __init__(
        self,
        http: httpx.AsyncClient,
        limiters: HostLimiters,
        *,
        default_headers: Mapping[str, str] | None = None,
        max_attempts: int = 2,
        backoff_seconds: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._http = http
        self._headers = dict(default_headers or {})
        self._limiters = limiters
        self._max_attempts = max_attempts
        self._backoff = backoff_seconds
        self._sleep = sleep

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        what: str = "",
    ) -> WebPage:
        return await self._request("GET", url, params=params, headers=headers, what=what)

    async def post(
        self,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        what: str = "",
    ) -> WebPage:
        return await self._request("POST", url, data=data, headers=headers, what=what)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        what: str = "",
    ) -> WebPage:
        name = what or urlsplit(url).netloc
        limiter = self._limiters.for_host(urlsplit(url).netloc)
        for attempt in range(1, self._max_attempts + 1):
            await limiter.wait()
            try:
                response = await self._http.request(
                    method,
                    url,
                    params=dict(params or {}),
                    data=dict(data) if data is not None else None,
                    headers={**self._headers, **(headers or {})},
                )
            except httpx.HTTPError as exc:
                if attempt == self._max_attempts:
                    raise PlatformUnavailableError(
                        messages.no_answer(name), detail=f"{url}: {type(exc).__name__}"
                    ) from None
                await self._pause(name, attempt, type(exc).__name__)
                continue
            if response.status_code >= 500 and attempt < self._max_attempts:
                await self._pause(name, attempt, f"HTTP {response.status_code}")
                continue
            return check_response(
                WebPage(
                    url=str(response.url),
                    status=response.status_code,
                    text=response.text,
                    content_type=response.headers.get("content-type", ""),
                    headers=dict(response.headers),
                ),
                name,
                retry_after=response.headers.get("retry-after"),
            )
        raise PlatformUnavailableError(messages.no_answer(name), detail=url)  # недостижимо

    async def _pause(self, name: str, attempt: int, reason: str) -> None:
        delay = self._backoff * 2 ** (attempt - 1)
        logger.warning("%s: %s, повтор через %.1f с", name, reason, delay)
        await self._sleep(delay)


def check_response(page: WebPage, name: str, retry_after: str | None = None) -> WebPage:
    """Статус и признаки анти-бота → ошибка сервиса; иначе страница как есть."""
    detail = f"{page.url}: HTTP {page.status}"
    if page.status in (404, 410):
        raise SourceNotFoundError(f"{name}: страница не найдена", detail=detail)
    if page.status == 429:
        wait = f", просит подождать {retry_after} с" if retry_after else ""
        raise RateLimitedError(messages.too_many_requests(name), detail=detail + wait)
    if page.status == 403:
        raise PlatformUnavailableError(BLOCKED.format(name=name), detail=f"{detail}, анти-бот?")
    if page.status >= 500:
        raise PlatformUnavailableError(messages.no_answer(name), detail=detail)
    if page.status >= 400:
        raise PlatformUnavailableError(messages.bad_answer(name), detail=detail)
    if looks_like_antibot(page.text):
        raise PlatformUnavailableError(
            BLOCKED.format(name=name), detail=f"{page.url}: страница анти-бота «не робот»"
        )
    return page


# 403 и страница «не робот»: площадка приняла нас за бота
BLOCKED = "{name}: площадка временно ограничила доступ (проверка «не робот»), повторите позже"


def looks_like_antibot(text: str) -> bool:
    if len(text) > ANTIBOT_SCAN_LIMIT:
        return False
    lower = text.lower()
    return any(marker in lower for marker in ANTIBOT_MARKERS)
