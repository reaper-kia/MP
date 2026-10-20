"""Сквозные поведения Mediator: лог с временем выполнения и кэш ответов.

Регистрируются в dependencies.build_mediator; хэндлеры про них не знают.
"""

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from collector_service.applications.mediator import Next, Query
from collector_service.applications.ports.cache import Cache
from collector_service.domain.exceptions import log_text

logger = logging.getLogger("collector_service.queries")


class LoggingBehavior:
    """Одна строка на запрос: какой, request_id, сколько длился, чем кончился. Без текстов."""

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock

    async def __call__(self, query: Query[Any], call_next: Next) -> Any:
        name = type(query).__name__
        ctx = getattr(query, "ctx", None)
        request_id = getattr(ctx, "request_id", "") or "-"
        started = self._clock()
        try:
            result = await call_next()
        except Exception as exc:
            logger.warning(
                "%s request_id=%s failed in %.2fs: %s: %s",
                name,
                request_id,
                self._clock() - started,
                type(exc).__name__,
                log_text(exc),
            )
            raise
        logger.info("%s request_id=%s done in %.2fs", name, request_id, self._clock() - started)
        return result


@runtime_checkable
class Cacheable(Protocol):
    """Запрос, ответ на который можно переиспользовать. None — этот экземпляр не кэшировать."""

    def cache_key(self) -> str | None: ...


class CachingBehavior:
    """Успешный ответ на Cacheable-запрос живёт в кэше ttl_seconds. Ошибки не кэшируются:
    площадка могла просто моргнуть."""

    def __init__(self, cache: Cache, ttl_seconds: float) -> None:
        self._cache = cache
        self._ttl = ttl_seconds

    async def __call__(self, query: Query[Any], call_next: Next) -> Any:
        key = query.cache_key() if isinstance(query, Cacheable) else None
        if key is None:
            return await call_next()
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = await call_next()
        self._cache.set(key, result, self._ttl)
        return result
