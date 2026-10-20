"""Порт applications/ports/search_cache.SearchCache: Redis и «кэш выключен» (B2-20).

Fail-open: Redis упал или не ответил за 200 мс — промах, в лог WARNING «cache unavailable»,
поиск идёт как обычно. Пользователь ошибки не видит.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable
from typing import Any, Protocol

import structlog

log = structlog.get_logger()

DEFAULT_TIMEOUT = 0.2


class RedisLike(Protocol):
    """То, что нужно от redis.asyncio.Redis (в тестах — фейк)."""

    def get(self, name: str) -> Awaitable[Any]: ...
    def set(self, name: str, value: str, *, ex: int | None = None) -> Awaitable[Any]: ...
    def ping(self) -> Awaitable[Any]: ...


class RedisSearchCache:
    def __init__(
        self, client: RedisLike, ttl_seconds: int, timeout_seconds: float = DEFAULT_TIMEOUT
    ) -> None:
        self._client = client
        self._ttl = max(1, int(ttl_seconds))
        self._timeout = timeout_seconds

    @property
    def enabled(self) -> bool:
        return True

    async def get(self, key: str) -> uuid.UUID | None:
        try:
            async with asyncio.timeout(self._timeout):
                raw = await self._client.get(key)
        except Exception as e:  # noqa: BLE001 — любая беда Redis = промах
            log.warning("cache unavailable", op="get", key=key, error=type(e).__name__)
            return None
        if raw is None:
            return None
        try:
            return uuid.UUID(raw.decode() if isinstance(raw, bytes) else str(raw))
        except ValueError:
            log.warning("cache record unreadable", key=key)
            return None

    async def put(self, key: str, search_id: uuid.UUID) -> None:
        try:
            async with asyncio.timeout(self._timeout):
                await self._client.set(key, str(search_id), ex=self._ttl)
        except Exception as e:  # noqa: BLE001
            log.warning("cache unavailable", op="set", key=key, error=type(e).__name__)
            return
        log.info("cache store", key=key, search_id=str(search_id), ttl=self._ttl)

    async def ping(self) -> bool:
        try:
            async with asyncio.timeout(self._timeout):
                await self._client.ping()
        except Exception:  # noqa: BLE001
            return False
        return True


class DisabledSearchCache:
    """CACHE_ENABLED=false: всё как до B2-20."""

    @property
    def enabled(self) -> bool:
        return False

    async def get(self, key: str) -> uuid.UUID | None:
        return None

    async def put(self, key: str, search_id: uuid.UUID) -> None:
        return None

    async def ping(self) -> bool:
        return False
