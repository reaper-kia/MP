"""Кэши в памяти процесса. Своей БД у сервиса нет, перезапуск кэш сбрасывает — это нормально."""

import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from collector_service.domain.enums import Health
from collector_service.domain.value_objects import PlatformInfo


class TtlCache:
    """Реализация порта applications/ports/cache.Cache: TTL на запись, не больше max_items
    записей (самые старые вытесняются)."""

    def __init__(self, max_items: int = 2048, clock: Callable[[], float] = time.monotonic) -> None:
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max = max_items
        self._clock = clock

    async def get(self, key: str) -> Any | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        expires, value = entry
        if self._clock() >= expires:
            del self._items[key]
            return None
        return value

    async def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        self._items[key] = (self._clock() + ttl_seconds, value)
        self._items.move_to_end(key)
        while len(self._items) > self._max:
            self._items.popitem(last=False)


HEALTH_OK_TTL = 300.0  # «здорова» — 5 минут (B1-07)
HEALTH_FAIL_TTL = 60.0  # проблему перепроверяем чаще: она может пройти сама


class HealthCache:
    """Кэш проверки площадки: здорова — 5 минут, проблема — 1 минута. Одна на коннектор."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entry: tuple[float, PlatformInfo] | None = None

    async def get(self, check: Callable[[], Awaitable[PlatformInfo]]) -> PlatformInfo:
        now = self._clock()
        if self._entry is not None and now < self._entry[0]:
            return self._entry[1]
        info = await check()
        ttl = HEALTH_OK_TTL if info.health is Health.OK else HEALTH_FAIL_TTL
        self._entry = (now + ttl, info)
        return info
