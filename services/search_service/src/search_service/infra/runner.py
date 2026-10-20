"""SearchRunner: реестр asyncio.Task по search_id + глобальный семафор."""
from __future__ import annotations

import asyncio
import uuid

import structlog

from search_service.applications.handlers.pipeline import Pipeline
from search_service.domain.enums import SearchStatus

log = structlog.get_logger()

# Глобальный семафор: только 1 активный пайплайн одновременно (B2-15)
GLOBAL_PIPELINE_SEMAPHORE: asyncio.Semaphore = asyncio.Semaphore(1)


class SearchRunner:
    def __init__(self, pipeline: Pipeline) -> None:
        self.pipeline = pipeline
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}

    async def launch(self, search_id: uuid.UUID) -> None:
        if search_id in self._tasks and not self._tasks[search_id].done():
            log.info("search already running", search_id=str(search_id))
            return

        async def _run_with_queue() -> None:
            log.info("search waiting for global slot", search_id=str(search_id))
            async with GLOBAL_PIPELINE_SEMAPHORE:
                log.info("search started execution", search_id=str(search_id))
                try:
                    await self.pipeline.run(search_id)
                except Exception as e:
                    log.exception("search crashed", search_id=str(search_id), exc=e)
                finally:
                    self._tasks.pop(search_id, None)
                    log.info("search finished and released slot", search_id=str(search_id))

        task: asyncio.Task[None] = asyncio.create_task(_run_with_queue())
        self._tasks[search_id] = task

    async def cancel(self, search_id: uuid.UUID) -> None:
        task = self._tasks.get(search_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def cancel_all(self) -> None:
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
        self._tasks.clear()