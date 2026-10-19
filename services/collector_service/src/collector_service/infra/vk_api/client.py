"""Вызов методов VK API. Знает про сеть и ошибки VK, но не про посты и группы.

Токен уходит только в теле POST: в URL его нет, значит и в логах httpx он не появится.
Ошибки VK превращаются в ошибки сервиса (domain/exceptions.py), коды — по задаче B1-03.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from collector_service.domain.exceptions import (
    CollectorError,
    PlatformUnavailableError,
    RateLimitedError,
    SourceNotFoundError,
    SourcePrivateError,
)
from collector_service.infra.vk_api.limiter import RateLimiter
from collector_service.infra.vk_api.transport import FormPoster, TransportError

logger = logging.getLogger(__name__)

VK_API_URL = "https://api.vk.com/method/"

RETRY_CODES = frozenset({6, 10})  # 6 — слишком много запросов, 10 — внутренняя ошибка VK
FLOOD_CODES = frozenset({6, 9, 29})  # лимиты: после ретраев → RATE_LIMITED
NO_ACCESS_CODES = frozenset({15, 18, 30})  # доступ запрещён / страница удалена / профиль закрыт
NOT_FOUND_CODES = frozenset({100, 113})  # неверный параметр / неверный id

type Param = str | int


class VkApiClient:
    def __init__(
        self,
        poster: FormPoster,
        *,
        token: str,
        version: str,
        limiter: RateLimiter,
        max_attempts: int = 4,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._poster = poster
        self._token = token
        self._version = version
        self._limiter = limiter
        self._max_attempts = max_attempts
        self._backoff = backoff_seconds
        self._sleep = sleep

    @property
    def configured(self) -> bool:
        return bool(self._token)

    async def call(self, method: str, **params: Param) -> Any:
        """Поле `response` ответа VK. Любая неудача — исключение из domain/exceptions.py."""
        if not self.configured:
            raise PlatformUnavailableError("ВКонтакте: не настроен доступ (VK_SERVICE_TOKEN)")
        form = {k: str(v) for k, v in params.items()}
        form["access_token"] = self._token
        form["v"] = self._version

        for attempt in range(1, self._max_attempts + 1):
            last = attempt == self._max_attempts
            await self._limiter.wait()
            try:
                payload = await self._poster.post_form(VK_API_URL + method, form)
            except TransportError as exc:
                if last:
                    raise PlatformUnavailableError(f"ВКонтакте не отвечает ({exc})") from None
                await self._retry_pause(method, attempt, f"сеть: {exc}")
                continue

            error = payload.get("error") if isinstance(payload, dict) else None
            if error is None:
                if isinstance(payload, dict) and "response" in payload:
                    return payload["response"]
                raise PlatformUnavailableError(f"ВКонтакте: неожиданный ответ на {method}")

            code = _error_code(error)
            if code in RETRY_CODES and not last:
                await self._retry_pause(method, attempt, f"ошибка VK {code}")
                continue
            raise _to_domain_error(method, code)

        raise PlatformUnavailableError(f"ВКонтакте: {method} не удался")  # недостижимо

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
    if code == 5:
        return PlatformUnavailableError("ВКонтакте: ключ доступа недействителен (ошибка 5)")
    if code in NO_ACCESS_CODES:
        return SourcePrivateError(f"ВКонтакте: страница закрыта, удалена или недоступна ({code})")
    if code in NOT_FOUND_CODES:
        return SourceNotFoundError(f"ВКонтакте: источник не найден ({code})")
    if code in FLOOD_CODES:
        return RateLimitedError(f"ВКонтакте: превышен лимит запросов ({code})")
    return PlatformUnavailableError(f"ВКонтакте: ошибка {code} в методе {method}")
