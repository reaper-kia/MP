"""Порты к площадкам. Реализации — infra/connectors/ (фейк для разработки — fake.py).

Сбор и поиск — потоки страниц (AsyncIterator[Page]): коннектор не знает про лимит постов и
бюджет времени, он просто отдаёт страницу за страницей. Останавливает его потребитель
(applications/collecting.py) — тогда следующая страница с площадки не запрашивается.
"""

from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from collector_service.domain.enums import Platform
from collector_service.domain.value_objects import (
    Page,
    Period,
    PlatformInfo,
    RawPost,
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

    def collect(
        self,
        source_external_id: str,
        period: Period,
        keywords: Sequence[str],
    ) -> AsyncIterator[Page]:
        """Посты одного источника за период (режим «по выбранным источникам»)."""
        ...

    def search(
        self,
        queries: Sequence[str],
        period: Period,
        region_terms: Sequence[str],
    ) -> AsyncIterator[Page]:
        """Поиск по всей площадке (режим «везде»)."""
        ...


class PostReader(Protocol):
    """Открыть один пост по ссылке и достать текст и дату со страницы площадки.

    Нужен глобальному поиску через поисковик: ссылка из выдачи сама по себе ничего не
    подтверждает — пост попадает в ответ, только если его удалось открыть (B1-06).
    """

    platform: Platform

    def accepts(self, url: str) -> bool:
        """Похоже ли на ссылку на пост этой площадки (а не на группу или профиль)."""
        ...

    async def read_post(self, url: str) -> RawPost | None:
        """None — страница открылась, но поста на ней нет (удалён, это не пост)."""
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
