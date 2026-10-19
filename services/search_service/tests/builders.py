"""Сборка поиска, источников и постов для тестов пайплайна и скоринга."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from search_service.applications.ports.collector_client import RawPost
from search_service.domain.entities import Publication, Search, SearchResult, SearchTarget, Source
from search_service.domain.enums import DateStatus, SearchMode, TargetKind
from search_service.domain.value_objects import Period
from tests.fakes import InMemoryUoW

NOW = datetime.now(UTC)


def period() -> Period:
    return Period((NOW - timedelta(days=30)).date(), NOW.date())


def raw_post(
    n: int, text: str | None = None, source: str = "s1", days_ago: int = 1, **extra: object
) -> RawPost:
    base: dict[str, object] = dict(
        platform="vk",
        source_external_id=source,
        post_external_id=str(n),
        url=f"https://vk.com/wall{source}_{n}",
        source_name=f"Источник {source}",
        source_url=f"https://vk.com/{source}",
        text=text if text is not None else f"Пост номер {n} про дороги",
        published_at=NOW - timedelta(days=days_ago),
    )
    base.update(extra)
    return RawPost(**base)  # type: ignore[arg-type]


async def add_source(uow: InMemoryUoW, external_id: str, *, is_regional: bool = True) -> Source:
    source = Source(
        platform="vk",
        external_id=external_id,
        screen_name=external_id,
        url=f"https://vk.com/{external_id}",
        name=f"Источник {external_id}",
        is_regional=is_regional,
    )
    await uow.sources.add(source)
    return source


async def add_search(
    uow: InMemoryUoW,
    sources: list[Source],
    mode: SearchMode = SearchMode.SELECTED,
) -> Search:
    """Поиск с одной целью-источником на каждый источник; всё уже лежит в in-memory БД."""
    search = Search(
        query="безопасность дорожного движения",
        period=period(),
        mode=mode,
        platforms=list(dict.fromkeys(s.platform for s in sources)),
    )
    search.targets = [
        SearchTarget(
            kind=TargetKind.SOURCE,
            platform=s.platform,
            name=s.name,
            url=s.url,
            source_id=s.id,
            search_id=search.id,
        )
        for s in sources
    ]
    await uow.searches.add(search)
    for t in search.targets:
        await uow.targets.add(t)
    return search


async def add_result(
    uow: InMemoryUoW,
    search: Search,
    target: SearchTarget,
    n: int,
    text: str,
    *,
    region_by_source: bool = True,
    source: str = "s1",
) -> SearchResult:
    """Уже сохранённый пост (publication + result без оценки) — вход для ScoringHandler."""
    pub = Publication(
        platform="vk",
        source_external_id=source,
        post_external_id=str(n),
        url=f"https://vk.com/wall{source}_{n}",
        source_name=f"Источник {source}",
        source_url=f"https://vk.com/{source}",
        text=text,
        published_at=NOW - timedelta(days=1),
    )
    pub = await uow.publications.upsert(pub)
    result = SearchResult(
        search_id=search.id,
        publication_id=pub.id,
        target_id=target.id,
        date_status=DateStatus.IN_PERIOD,
        region_by_source=region_by_source,
    )
    await uow.results.add(result)
    return result
