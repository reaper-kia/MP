from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from search_service.applications.ports.uow import UnitOfWork as UoWProtocol
from search_service.infra.database.repositories import (
    PublicationRepo,
    ResultRepo,
    SearchRepo,
    SourceRepo,
    TargetRepo,
)


class UnitOfWork(UoWProtocol):
    def __init__(self, session: AsyncSession):
        self._session = session
        self.sources = SourceRepo(session)
        self.searches = SearchRepo(session)
        self.targets = TargetRepo(session)
        self.publications = PublicationRepo(session)
        self.results = ResultRepo(session)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type:
            await self.rollback()
        else:
            await self.commit()

    async def commit(self):
        await self._session.commit()

    async def rollback(self):
        await self._session.rollback()
