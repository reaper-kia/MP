from types import TracebackType
from typing import Protocol, Self


class UnitOfWork(Protocol):
    """Транзакция над search_db.

    TODO(B2-01): добавить репозитории как атрибуты (таблицы — ARCHITECTURE §4, B2-01):
        sources: SourceRepository
        searches: SearchRepository
        targets: SearchTargetRepository
        publications: PublicationRepository
        results: SearchResultRepository
    Протоколы репозиториев — в applications/ports/repositories.py, реализации — infra/repositories/.
    """

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...
