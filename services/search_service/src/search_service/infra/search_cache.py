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

from search_service.applications.search_cache import running_key

log = structlog.get_logger()

DEFAULT_TIMEOUT = 0.2
# отметка «идёт» живёт не дольше самого долгого поиска; снимается в конце пайплайна
RUNNING_TTL_SECONDS = 1200


class RedisLike(Protocol):
    """То, что нужно от redis.asyncio.Redis (в тестах — фейк)."""

    def get(self, name: str) -> Awaitable[Any]: ...
    def set(self, name: str, value: str, *, ex: int | None = None) -> Awaitable[Any]: ...
    def delete(self, *names: str) -> Awaitable[Any]: ...
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
        return await self._read(key)

    async def put(self, key: str, search_id: uuid.UUID) -> None:
        if await self._write(key, search_id, self._ttl):
            log.info("cache store", key=key, search_id=str(search_id), ttl=self._ttl)

    async def get_running(self, key: str) -> uuid.UUID | None:
        return await self._read(running_key(key))

    async def put_running(self, key: str, search_id: uuid.UUID) -> None:
        await self._write(running_key(key), search_id, RUNNING_TTL_SECONDS)

    async def drop_running(self, key: str, search_id: uuid.UUID) -> None:
        """Снять отметку, только если она всё ещё про этот поиск (а не про более новый)."""
        name = running_key(key)
        if await self._read(name) != search_id:
            return
        try:
            async with asyncio.timeout(self._timeout):
                await self._client.delete(name)
        except Exception as e:  # noqa: BLE001
            log.warning("cache unavailable", op="delete", key=name, error=type(e).__name__)

    async def _read(self, name: str) -> uuid.UUID | None:
        try:
            async with asyncio.timeout(self._timeout):
                raw = await self._client.get(name)
        except Exception as e:  # noqa: BLE001 — любая беда Redis = промах
            log.warning("cache unavailable", op="get", key=name, error=type(e).__name__)
            return None
        if raw is None:
            return None
        try:
            return uuid.UUID(raw.decode() if isinstance(raw, bytes) else str(raw))
        except ValueError:
            log.warning("cache record unreadable", key=name)
            return None

    async def _write(self, name: str, search_id: uuid.UUID, ttl: int) -> bool:
        try:
            async with asyncio.timeout(self._timeout):
                await self._client.set(name, str(search_id), ex=ttl)
        except Exception as e:  # noqa: BLE001
            log.warning("cache unavailable", op="set", key=name, error=type(e).__name__)
            return False
        return True

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

    async def get_running(self, key: str) -> uuid.UUID | None:
        return None

    async def put_running(self, key: str, search_id: uuid.UUID) -> None:
        return None

    async def drop_running(self, key: str, search_id: uuid.UUID) -> None:
        return None

    async def ping(self) -> bool:
        return False
