from collections.abc import Sequence
from typing import Protocol

from collector_service.errors import NotImplementedYetError
from collector_service.models import (
    CollectResult,
    Health,
    Period,
    Platform,
    PlatformInfo,
    SourceInfo,
)


class PlatformConnector(Protocol):
    """Одна площадка. Возвращает только реально полученные данные (ARCHITECTURE §5)."""

    platform: Platform
    title: str
    # Хосты ссылок этой площадки: по ним registry определяет площадку для ResolveSource
    hosts: tuple[str, ...]

    async def health(self) -> PlatformInfo: ...

    async def resolve(self, url: str) -> SourceInfo:
        """Ссылка (уже нормализованная) → карточка источника. UnsupportedUrl / SourceNotFound."""
        ...

    async def collect(
        self,
        source_external_id: str,
        period: Period,
        keywords: Sequence[str],
        max_posts: int,
    ) -> CollectResult:
        """Посты одного источника за период (режим «по выбранным источникам»)."""
        ...

    async def search(
        self,
        queries: Sequence[str],
        period: Period,
        region_terms: Sequence[str],
        max_posts: int,
    ) -> CollectResult:
        """Поиск по всей площадке (режим «везде»)."""
        ...


class NotImplementedConnector:
    """База для коннектора, который ещё пишется: всё честно отвечает «не реализовано»."""

    platform: Platform
    title: str
    hosts: tuple[str, ...] = ()
    task: str = ""  # какая задача из docs/tasks его делает

    async def health(self) -> PlatformInfo:
        return PlatformInfo(
            platform=self.platform,
            title=self.title,
            source_mode_supported=False,
            global_mode_supported=False,
            health=Health.UNAVAILABLE,
            note="Площадка ещё не подключена",
        )

    async def resolve(self, url: str) -> SourceInfo:
        raise NotImplementedYetError(f"{self.title}: resolve не реализован ({self.task})")

    async def collect(
        self,
        source_external_id: str,
        period: Period,
        keywords: Sequence[str],
        max_posts: int,
    ) -> CollectResult:
        raise NotImplementedYetError(f"{self.title}: collect не реализован ({self.task})")

    async def search(
        self,
        queries: Sequence[str],
        period: Period,
        region_terms: Sequence[str],
        max_posts: int,
    ) -> CollectResult:
        raise NotImplementedYetError(f"{self.title}: search не реализован ({self.task})")
