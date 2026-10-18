"""Unit of Work поверх AsyncSession.

Сервис наследуется и создаёт свои репозитории в `_init_repositories`:

    class SqlAlchemyUnitOfWork(BaseSqlAlchemyUnitOfWork):
        items: ItemRepository

        def _init_repositories(self, session: AsyncSession) -> None:
            self.items = SqlAlchemyItemRepository(session)

    async with uow_factory() as uow:
        uow.items.add(item)
        await uow.commit()       # без commit → rollback при выходе
"""

from types import TracebackType
from typing import Protocol, Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class UnitOfWork(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class BaseSqlAlchemyUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("UnitOfWork is not entered")
        return self._session

    def _init_repositories(self, session: AsyncSession) -> None:
        raise NotImplementedError

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self._init_repositories(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            await self.rollback()  # no-op после commit
        finally:
            await self.session.close()
            self._session = None

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
