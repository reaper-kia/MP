from __future__ import annotations

import asyncio
import uuid

import structlog

from search_service.applications.handlers.pipeline import Pipeline

log = structlog.get_logger()


class SearchRunner:
    """Реестр asyncio.Task по search_id, запуск/отмена.

    Очередь (B2-15): одновременно идут не больше max_parallel пайплайнов (SEARCH_MAX_PARALLEL,
    по умолчанию 1) — модели на одной видеокарте, параллельные поиски только мешают друг другу и
    уходят в эвристику по бюджету. Остальные ждут со статусом queued; отмена в очереди работает.
    """

    def __init__(self, pipeline: Pipeline, max_parallel: int = 1) -> None:
        self.pipeline = pipeline
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._slots = asyncio.Semaphore(max(1, max_parallel))

    async def launch(self, search_id: uuid.UUID) -> None:
        if search_id in self._tasks and not self._tasks[search_id].done():
            return
        task = asyncio.create_task(self._run(search_id))
        self._tasks[search_id] = task

        def _done(t: asyncio.Task[None]) -> None:
            self._tasks.pop(search_id, None)
            if t.cancelled():
                log.info("search cancelled", search_id=str(search_id))
            elif t.exception():
                log.exception("search crashed", search_id=str(search_id), exc=t.exception())

        task.add_done_callback(_done)

    async def _run(self, search_id: uuid.UUID) -> None:
        if self._slots.locked():
            log.info("search queued", search_id=str(search_id))
        async with self._slots:
            await self.pipeline.run(search_id)

    async def cancel(self, search_id: uuid.UUID) -> None:
        task = self._tasks.get(search_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def cancel_all(self) -> None:
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
        self._tasks.clear()
