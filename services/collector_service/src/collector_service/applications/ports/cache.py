from typing import Any, Protocol


class Cache(Protocol):
    """Кэш с временем жизни записи. Реализация — infra/cache.py (в памяти процесса)."""

    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any, ttl_seconds: float) -> None: ...
