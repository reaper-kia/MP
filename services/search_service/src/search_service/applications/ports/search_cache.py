from __future__ import annotations

import uuid
from typing import Protocol


class SearchCache(Protocol):
    """Кэш готовых подборок (B2-20): ключ параметров поиска → id готового поиска.

    Реализации — infra/search_cache.py: Redis и «выключено» (CACHE_ENABLED=false). Недоступный
    Redis — промах и WARNING в лог, а не ошибка: поиск идёт как обычно (fail-open).
    """

    @property
    def enabled(self) -> bool: ...
    async def get(self, key: str) -> uuid.UUID | None: ...
    async def put(self, key: str, search_id: uuid.UUID) -> None: ...
    async def ping(self) -> bool: ...

    # «Такой же поиск уже идёт» (B2-20 P2): отметка ключ → id поиска, который собирает подборку.
    # Повтор не запускает второй сбор, а ждёт этот поиск и получает копию его подборки.
    async def get_running(self, key: str) -> uuid.UUID | None: ...
    async def put_running(self, key: str, search_id: uuid.UUID) -> None: ...
    async def drop_running(self, key: str, search_id: uuid.UUID) -> None: ...
