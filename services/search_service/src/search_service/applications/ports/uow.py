from __future__ import annotations

from types import TracebackType
from typing import Protocol

from search_service.applications.ports.repositories import (
    PublicationRepository,
    ResultRepository,
    SearchRepository,
    SourceRepository,
    TargetRepository,
)


class UnitOfWork(Protocol):
    # только чтение: реализация может отдавать репозитории текущей сессии
    @property
    def sources(self) -> SourceRepository: ...
    @property
    def searches(self) -> SearchRepository: ...
    @property
    def targets(self) -> TargetRepository: ...
    @property
    def publications(self) -> PublicationRepository: ...
    @property
    def results(self) -> ResultRepository: ...

    async def __aenter__(self) -> UnitOfWork: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
