from __future__ import annotations

from typing import Protocol

from search_service.applications.ports.repositories import (
    PublicationRepository,
    ResultRepository,
    SearchRepository,
    SourceRepository,
    TargetRepository,
)


class UnitOfWork(Protocol):
    sources: SourceRepository
    searches: SearchRepository
    targets: TargetRepository
    publications: PublicationRepository
    results: ResultRepository

    async def __aenter__(self) -> UnitOfWork: ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
