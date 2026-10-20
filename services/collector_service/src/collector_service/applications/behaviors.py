"""Сквозные поведения Mediator: лог с временем выполнения и кэш ответов.

Регистрируются в dependencies.build_mediator; хэндлеры про них не знают.
"""

import logging
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from collector_service.applications.mediator import Next, Query
from collector_service.applications.ports.cache import Cache
from collector_service.domain.exceptions import log_text

logger = logging.getLogger("collector_service.queries")
cache_logger = logging.getLogger("collector_service.cache")


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
    """Успешный ответ на Cacheable-запрос живёт в кэше ttl секунд. Ошибки не кэшируются:
    площадка могла просто моргнуть. Оборванный сбор (`complete=False`: кончился бюджет времени,
    площадка упала посреди сбора) — тоже.

    ttl_by_type — своё время жизни для типа запроса (посты — 10 мин, карточка источника — 10 мин,
    B2-20); ttl <= 0 — этот тип не кэшируем (CACHE_ENABLED=false для сбора).
    Кэш недоступен — реализация порта отвечает промахом, запрос идёт на площадку (fail-open).
    """

    def __init__(
        self,
        cache: Cache,
        ttl_seconds: float,
        ttl_by_type: Mapping[type[Any], float] | None = None,
    ) -> None:
        self._cache = cache
        self._ttl = ttl_seconds
        self._ttl_by_type = dict(ttl_by_type or {})

    async def __call__(self, query: Query[Any], call_next: Next) -> Any:
        key = query.cache_key() if isinstance(query, Cacheable) else None
        ttl = self._ttl_by_type.get(type(query), self._ttl)
        if key is None or ttl <= 0:
            return await call_next()
        cached = await self._cache.get(key)
        if cached is not None:
            cache_logger.info("cache hit key=%s", key)
            return cached
        cache_logger.info("cache miss key=%s", key)
        result = await call_next()
        if getattr(result, "complete", True):
            await self._cache.set(key, result, ttl)
            cache_logger.info("cache store key=%s ttl=%.0fs", key, ttl)
        return result
