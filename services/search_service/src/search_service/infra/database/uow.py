from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from search_service.infra.database.repositories import (
    PublicationRepo,
    ResultRepo,
    SearchRepo,
    SourceRepo,
    TargetRepo,
)


@dataclass
class _Scope:
    """Сессия и репозитории одного входа в `async with uow:`."""

    session: AsyncSession
    sources: SourceRepo
    searches: SearchRepo
    targets: TargetRepo
    publications: PublicationRepo
    results: ResultRepo
    token: Token[_Scope | None] | None = None


class UnitOfWork:
    """Каждый вход (async with uow:) открывает свою сессию из фабрики.

    Текущая сессия хранится в ContextVar, поэтому один объект UoW можно делить
    между параллельными задачами пайплайна (asyncio.gather): у каждой задачи
    свой контекст и своя сессия. Вложенный вход открывает новую сессию и
    при выходе возвращает внешнюю.
    """

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker
        self._scope: ContextVar[_Scope | None] = ContextVar(f"uow_scope_{id(self)}", default=None)

    def _current(self) -> _Scope:
        scope = self._scope.get()
        if scope is None:
            raise RuntimeError("UnitOfWork используется вне `async with uow:`")
        return scope

    @property
    def sources(self) -> SourceRepo:
        return self._current().sources

    @property
    def searches(self) -> SearchRepo:
        return self._current().searches

    @property
    def targets(self) -> TargetRepo:
        return self._current().targets

    @property
    def publications(self) -> PublicationRepo:
        return self._current().publications

    @property
    def results(self) -> ResultRepo:
        return self._current().results

    async def __aenter__(self) -> UnitOfWork:
        session = self._session_maker()
        scope = _Scope(
            session=session,
            sources=SourceRepo(session),
            searches=SearchRepo(session),
            targets=TargetRepo(session),
            publications=PublicationRepo(session),
            results=ResultRepo(session),
        )
        scope.token = self._scope.set(scope)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        scope = self._current()
        try:
            if exc_type:
                await self.rollback()
            else:
                await self.commit()
        finally:
            await scope.session.close()
            if scope.token is not None:
                self._scope.reset(scope.token)

    async def commit(self) -> None:
        await self._current().session.commit()

    async def rollback(self) -> None:
        await self._current().session.rollback()
