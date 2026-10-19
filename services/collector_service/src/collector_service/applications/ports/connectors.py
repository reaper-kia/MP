"""Порты к площадкам. Реализации — infra/connectors/ (фейк для разработки — fake.py)."""

from collections.abc import Sequence
from typing import Protocol

from collector_service.domain.enums import Platform
from collector_service.domain.value_objects import (
    CollectResult,
    Period,
    PlatformInfo,
    SourceInfo,
)


class PlatformConnector(Protocol):
    """Одна площадка. Возвращает только реально полученные данные (ARCHITECTURE §5)."""

    platform: Platform
    title: str
    # Хосты ссылок этой площадки: по ним реестр определяет площадку для ResolveSource
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


class ConnectorRegistry(Protocol):
    """Где взять коннектор: по площадке или по ссылке."""

    def get(self, platform: Platform) -> PlatformConnector:
        """Нет такой площадки → InvalidRequestError."""
        ...

    def all(self) -> list[PlatformConnector]: ...

    def detect(self, url: str) -> PlatformConnector:
        """Площадка по хосту ссылки. Чужой хост → UnsupportedUrlError."""
        ...
