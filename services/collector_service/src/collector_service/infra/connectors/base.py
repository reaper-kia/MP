from collections.abc import AsyncIterator, Sequence

from collector_service.applications.exceptions import NotImplementedYetError
from collector_service.domain.enums import Health, Platform
from collector_service.domain.value_objects import (
    Page,
    Period,
    PlatformInfo,
    SourceInfo,
)


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
    ) -> AsyncIterator[Page]:
        raise NotImplementedYetError(f"{self.title}: collect не реализован ({self.task})")
        yield Page()  # pragma: no cover — делает метод асинхронным генератором

    async def search(
        self,
        queries: Sequence[str],
        period: Period,
        region_terms: Sequence[str],
    ) -> AsyncIterator[Page]:
        raise NotImplementedYetError(f"{self.title}: search не реализован ({self.task})")
        yield Page()  # pragma: no cover
