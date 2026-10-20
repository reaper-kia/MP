from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any

import structlog

from search_service.applications.handlers.pipeline import Pipeline

log = structlog.get_logger()

# повтор ждёт оригинал из другого процесса — опрашиваем базу; дольше 20 минут поиск не идёт
FOLLOW_POLL_SECONDS = 2.0
FOLLOW_MAX_SECONDS = 1200.0


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
        self._start(search_id, self._run(search_id))

    async def follow(self, search_id: uuid.UUID, leader_id: uuid.UUID) -> None:
        """Повтор ждёт такой же идущий поиск вне очереди (слот не занимает) и берёт его подборку."""
        self._start(search_id, self._follow(search_id, leader_id))

    def _start(self, search_id: uuid.UUID, work: Coroutine[Any, Any, None]) -> None:
        if search_id in self._tasks and not self._tasks[search_id].done():
            work.close()
            return
        task = asyncio.create_task(work)
        self._tasks[search_id] = task

        def _done(t: asyncio.Task[None]) -> None:
            self._tasks.pop(search_id, None)
            if t.cancelled():
                log.info("search cancelled", search_id=str(search_id))
            elif t.exception():
                log.exception("search crashed", search_id=str(search_id), exc=t.exception())

        task.add_done_callback(_done)

    async def _follow(self, search_id: uuid.UUID, leader_id: uuid.UUID) -> None:
        log.info("search joins running twin", search_id=str(search_id), leader_id=str(leader_id))
        leader = self._tasks.get(leader_id)
        if leader is not None and not leader.done():
            # asyncio.wait не отменяет оригинал, если отменят повтор
            await asyncio.wait([leader])
        else:
            waited = 0.0
            while waited < FOLLOW_MAX_SECONDS and not await self.pipeline.is_final(leader_id):
                await asyncio.sleep(FOLLOW_POLL_SECONDS)
                waited += FOLLOW_POLL_SECONDS
        if await self.pipeline.adopt(search_id, leader_id):
            return
        log.info("twin gave no selection, searching", search_id=str(search_id))
        await self.pipeline.forget_twin(search_id)
        await self._run(search_id)

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
