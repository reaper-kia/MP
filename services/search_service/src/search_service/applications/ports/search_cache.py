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
