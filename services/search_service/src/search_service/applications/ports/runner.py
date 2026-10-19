from __future__ import annotations

import uuid
from typing import Protocol


class SearchRunner(Protocol):
    """Фоновый запуск/отмена пайплайна поиска. Реализация — infra/runner.py."""

    async def launch(self, search_id: uuid.UUID) -> None: ...
    async def cancel(self, search_id: uuid.UUID) -> None: ...
