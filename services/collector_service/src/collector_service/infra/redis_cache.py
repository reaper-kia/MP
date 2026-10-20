"""Порт applications/ports/cache.Cache поверх Redis (B2-20): кэш переживает перезапуск сервиса.

Fail-open: Redis упал, не ответил за 200 мс или отдал непонятное — это промах, а не ошибка:
сбор идёт на площадку, в лог — WARNING «cache unavailable». Пользователь ошибки не видит.
"""

import asyncio
import logging
from collections.abc import Awaitable
from typing import Any, Protocol

from collector_service.infra.cache_codec import decode, encode

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 0.2


class RedisLike(Protocol):
    """То, что нужно от redis.asyncio.Redis (в тестах — фейк)."""

    def get(self, name: str) -> Awaitable[Any]: ...

    def set(self, name: str, value: bytes, *, px: int | None = None) -> Awaitable[Any]: ...


class RedisCache:
    def __init__(self, client: RedisLike, timeout_seconds: float = DEFAULT_TIMEOUT) -> None:
        self._client = client
        self._timeout = timeout_seconds

    async def get(self, key: str) -> Any | None:
        try:
            async with asyncio.timeout(self._timeout):
                data = await self._client.get(key)
        except Exception as exc:  # noqa: BLE001 — любая беда Redis = промах
            logger.warning("cache unavailable (get key=%s): %s", key, type(exc).__name__)
            return None
        if data is None:
            return None
        try:
            return decode(bytes(data))
        except Exception as exc:  # noqa: BLE001 — битая/чужая запись = промах
            logger.warning("cache record unreadable key=%s: %s", key, type(exc).__name__)
            return None

    async def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        try:
            payload = encode(value)
        except TypeError:
            logger.warning("cache: value of %s is not cacheable", type(value).__name__)
            return
        try:
            async with asyncio.timeout(self._timeout):
                await self._client.set(key, payload, px=max(1, int(ttl_seconds * 1000)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache unavailable (set key=%s): %s", key, type(exc).__name__)
