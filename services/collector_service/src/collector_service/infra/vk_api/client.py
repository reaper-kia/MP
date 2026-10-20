"""Вызов методов VK API. Знает про сеть и ошибки VK, но не про посты и группы.

Токен уходит только в теле POST: в URL его нет, значит и в логах httpx он не появится.
Токен берётся у TokenSource на каждый вызов: токен VK ID живёт час и обновляется сам (tokens.py);
на ошибку 5 клиент один раз просит новый токен и повторяет запрос.
Ошибки VK превращаются в ошибки сервиса (domain/exceptions.py), коды — по задаче B1-03.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from collector_service.domain import messages
from collector_service.domain.exceptions import (
    CollectorError,
    MethodUnavailableError,
    PlatformUnavailableError,
    RateLimitedError,
    SourceNotFoundError,
    SourcePrivateError,
)
from collector_service.infra.vk_api.limiter import RateLimiter
from collector_service.infra.vk_api.tokens import StaticToken, TokenSource
from collector_service.infra.vk_api.transport import FormPoster, TransportError

logger = logging.getLogger(__name__)

VK_API_URL = "https://api.vk.com/method/"

RETRY_CODES = frozenset({6, 10})  # 6 — слишком много запросов, 10 — внутренняя ошибка VK
FLOOD_CODES = frozenset({6, 9, 29})  # лимиты: после ретраев → RATE_LIMITED
NO_ACCESS_CODES = frozenset({15, 18, 30})  # доступ запрещён / страница удалена / профиль закрыт
NOT_FOUND_CODES = frozenset({100, 113})  # неверный параметр / неверный id
INVALID_TOKEN = 5
METHOD_UNAVAILABLE = 1051  # «Method is not available for this profile type» (newsfeed.search)
VK = "ВКонтакте"

type Param = str | int


class VkApiClient:
    def __init__(
        self,
        poster: FormPoster,
        *,
        token: str = "",
        tokens: TokenSource | None = None,
        version: str,
        limiter: RateLimiter,
        max_attempts: int = 4,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._poster = poster
        self._tokens: TokenSource = tokens if tokens is not None else StaticToken(token)
        self._version = version
        self._limiter = limiter
        self._max_attempts = max_attempts
        self._backoff = backoff_seconds
        self._sleep = sleep

    @property
    def configured(self) -> bool:
        return self._tokens.configured

    async def call(self, method: str, **params: Param) -> Any:
        """Поле `response` ответа VK. Любая неудача — исключение из domain/exceptions.py."""
        if not self.configured:
            raise PlatformUnavailableError(
                messages.not_configured(VK),
                detail="VK: нет ни VK_SERVICE_TOKEN, ни токена VK ID (scripts/vk_token.py)",
            )
        form = {k: str(v) for k, v in params.items()}
        form["access_token"] = await self._tokens.token()
        form["v"] = self._version
        refreshed = False
        attempt = 0

        while attempt < self._max_attempts:
            attempt += 1
            last = attempt == self._max_attempts
            await self._limiter.wait()
            try:
                payload = await self._poster.post_form(VK_API_URL + method, form)
            except TransportError as exc:
                if last:
                    raise PlatformUnavailableError(
                        messages.no_answer(VK), detail=f"VK {method}: сеть: {exc}"
                    ) from None
                await self._retry_pause(method, attempt, f"сеть: {exc}")
                continue

            error = payload.get("error") if isinstance(payload, dict) else None
            if error is None:
                if isinstance(payload, dict) and "response" in payload:
                    return payload["response"]
                raise PlatformUnavailableError(
                    messages.bad_answer(VK), detail=f"VK {method}: неожиданный ответ"
                )

            code = _error_code(error)
            if code == INVALID_TOKEN and self._tokens.refreshable and not refreshed:
                refreshed = True  # токен истёк раньше срока / отозван: один раз обновляем
                logger.warning("VK %s: ключ недействителен, обновляю токен VK ID", method)
                form["access_token"] = await self._tokens.refresh()
                attempt -= 1  # повтор после обновления токена не тратит попытку
                continue
            if code in RETRY_CODES and not last:
                await self._retry_pause(method, attempt, f"ошибка VK {code}")
                continue
            raise _to_domain_error(method, code)

        raise PlatformUnavailableError(messages.no_answer(VK), detail=f"VK {method}")  # недостижимо

    async def _retry_pause(self, method: str, attempt: int, reason: str) -> None:
        delay = self._backoff * 2 ** (attempt - 1)
        logger.warning(
            "VK %s: %s, повтор %d/%d через %.1f с",
            method,
            reason,
            attempt,
            self._max_attempts - 1,
            delay,
        )
        await self._sleep(delay)


def _error_code(error: Any) -> int:
    code = error.get("error_code") if isinstance(error, Mapping) else None
    return code if isinstance(code, int) else 0


def _to_domain_error(method: str, code: int) -> CollectorError:
    detail = f"VK {method}: ошибка {code}"
    if code == INVALID_TOKEN:
        return PlatformUnavailableError(messages.access_denied(VK), detail=detail)
    if code == METHOD_UNAVAILABLE:
        return MethodUnavailableError(
            f"{VK}: поиск по всей площадке закрыт для нашего ключа. {messages.VIA_YANDEX_NOTE}",
            detail=f"{detail} (метод недоступен для этого типа ключа)",
        )
    if code in NO_ACCESS_CODES:
        return SourcePrivateError(f"{VK}: страница закрыта, удалена или недоступна", detail=detail)
    if code in NOT_FOUND_CODES:
        return SourceNotFoundError(messages.source_not_found(VK), detail=detail)
    if code in FLOOD_CODES:
        return RateLimitedError(messages.too_many_requests(VK), detail=detail)
    if code in RETRY_CODES:
        return PlatformUnavailableError(messages.no_answer(VK), detail=detail)
    return PlatformUnavailableError(messages.bad_answer(VK), detail=detail)
