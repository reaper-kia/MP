from __future__ import annotations

import uuid

from search_service.applications.handlers.matched import recount_matched
from search_service.applications.ports.runner import SearchRunner
from search_service.applications.ports.uow import UnitOfWork
from search_service.domain.entities import Search
from search_service.domain.enums import SearchStatus, TargetStatus
from search_service.domain.errors import NotFoundError, SearchNotFinished


class ControlHandler:
    def __init__(self, uow: UnitOfWork, runner: SearchRunner) -> None:
        self.uow = uow
        self.runner = runner

    async def set_excluded(
        self, search_id: uuid.UUID, result_ids: list[uuid.UUID], excluded: bool
    ) -> dict[str, int]:
        async with self.uow:
            search = await self.uow.searches.get_by_id(search_id)
            if not search:
                raise NotFoundError("SEARCH_NOT_FOUND")
            results = await self.uow.results.get_by_search(search_id)
            by_id = {r.id: r for r in results}
            for rid in result_ids:
                r = by_id.get(rid)
                if not r:
                    raise NotFoundError("RESULT_NOT_FOUND")
                r.set_excluded(excluded)
                await self.uow.results.save(r)
            await self.uow.commit()
            counts = await self.uow.results.counts(search_id)
        # «в подборке N» в блоке «Где искали» не должно считать исключённые (B2-07)
        await recount_matched(self.uow, search_id)
        return counts

    async def retry(self, search_id: uuid.UUID, target_ids: list[uuid.UUID] | None) -> Search:
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                raise NotFoundError("SEARCH_NOT_FOUND")
            if not search.status.is_final:  # QUEUED или RUNNING
                raise SearchNotFinished("Поиск ещё выполняется")

            targets_to_retry = []
            if target_ids:
                by_id = {t.id: t for t in search.targets}
                for tid in target_ids:
                    t = by_id.get(tid)
                    if not t:
                        raise NotFoundError("TARGET_NOT_FOUND")
                    if t.status != TargetStatus.FAILED:
                        continue
                    targets_to_retry.append(t)
            else:
                targets_to_retry = [t for t in search.targets if t.status == TargetStatus.FAILED]

            if not targets_to_retry:
                return search

            for t in targets_to_retry:
                t.status = TargetStatus.PENDING
                t.error_code = None
                t.error_message = None
                t.finished_at = None
                await self.uow.targets.save(t)
            search.status = SearchStatus.QUEUED
            await self.uow.searches.save(search)
            await self.uow.commit()

        await self.runner.launch(search_id)
        async with self.uow:
            fresh = await self.uow.searches.get_with_targets(search_id)
            if not fresh:
                raise NotFoundError("SEARCH_NOT_FOUND")
            return fresh

    async def cancel(self, search_id: uuid.UUID) -> Search:
        async with self.uow:
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                raise NotFoundError("SEARCH_NOT_FOUND")
            await self.runner.cancel(search_id)
            search = await self.uow.searches.get_with_targets(search_id)
            if not search:
                raise NotFoundError("SEARCH_NOT_FOUND")
            if search.status not in {
                SearchStatus.COMPLETED,
                SearchStatus.PARTIAL,
                SearchStatus.FAILED,
                SearchStatus.CANCELLED,
            }:
                search.cancel()
                await self.uow.searches.save(search)
                # cancel() переводит незавершённые цели в SKIPPED — их тоже сохраняем
                for t in search.targets:
                    await self.uow.targets.save(t)
                await self.uow.commit()
            return search
