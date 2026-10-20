from typing import Any, Protocol


class Cache(Protocol):
    """Кэш с временем жизни записи. Реализации — infra/cache.py (в памяти процесса) и
    infra/redis_cache.py (Redis, общий для перезапусков). Недоступный кэш — промах, не ошибка."""

    async def get(self, key: str) -> Any | None: ...

    async def set(self, key: str, value: Any, ttl_seconds: float) -> None: ...
