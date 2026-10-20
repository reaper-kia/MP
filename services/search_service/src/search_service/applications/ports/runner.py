from __future__ import annotations

import uuid
from typing import Protocol


class SearchRunner(Protocol):
    """Фоновый запуск/отмена пайплайна поиска. Реализация — infra/runner.py."""

    async def launch(self, search_id: uuid.UUID) -> None: ...
    async def follow(self, search_id: uuid.UUID, leader_id: uuid.UUID) -> None:
        """Такой же поиск leader_id уже идёт: дождаться его и взять копию подборки; если он
        не дал подборки (failed / cancelled) — запустить свой пайплайн как обычно."""
        ...

    async def cancel(self, search_id: uuid.UUID) -> None: ...
