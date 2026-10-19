from __future__ import annotations

from typing import Protocol

from search_service.applications.ports.collector_client import RawPost
from search_service.applications.ports.uow import UnitOfWork
from search_service.domain.entities import (
    Publication,
    Search,
    SearchResult,
    SearchTarget,
    Source,
)
from search_service.domain.enums import DateStatus


class _Titled(Protocol):
    @property
    def title(self) -> str | None: ...
    @property
    def text(self) -> str: ...


def make_title(post: _Titled) -> tuple[str, str]:
    """Заголовок или начало текста (≤120 символов по границе слова): RawPost / Publication."""
    if post.title:
        return post.title, "title"
    text = post.text.strip()
    if len(text) <= 120:
        return text, "post_start"
    # граница слова
    cut = text[:120]
    last_space = cut.rfind(" ")
    if last_space > 60:
        cut = cut[:last_space]
    return cut + "…", "post_start"


class SaveHandler:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def save_posts(
        self, search: Search, target: SearchTarget, posts: list[RawPost]
    ) -> list[SearchResult]:
        """Upsert publications + insert results (без дублирования)."""
        async with self.uow:
            # кэш источников для region_by_source
            source_cache: dict[tuple[str, str], Source | None] = {}

            results: list[SearchResult] = []
            for post in posts:
                pub = Publication(
                    platform=post.platform,
                    source_external_id=post.source_external_id,
                    post_external_id=post.post_external_id,
                    url=post.url,
                    source_name=post.source_name,
                    source_url=post.source_url,
                    text=post.text,
                    title=post.title,
                    published_at=post.published_at,
                    metrics=post.metrics,
                    is_repost=post.is_repost,
                    repost_of_url=post.repost_of_url,
                )
                pub = await self.uow.publications.upsert(pub)

                # дедуп: тот же пост в том же поиске = пропуск
                exists = await self.uow.results.exists_in_search(search.id, pub.id)
                if exists:
                    continue

                # дата
                if post.published_at is None:
                    date_status = DateStatus.UNKNOWN
                elif search.period.contains(post.published_at):
                    date_status = DateStatus.IN_PERIOD
                else:
                    # вне периода — пропускаем
                    continue

                # region_by_source
                src_key = (post.platform, post.source_external_id)
                if src_key not in source_cache:
                    source_cache[src_key] = await self.uow.sources.get_by_key(*src_key)
                source = source_cache[src_key]
                region_by_source = bool(source and source.is_regional)

                result = SearchResult(
                    search_id=search.id,
                    publication_id=pub.id,
                    target_id=target.id,
                    date_status=date_status,
                    region_by_source=region_by_source,
                )
                await self.uow.results.add(result)
                results.append(result)

            await self.uow.commit()
            return results
