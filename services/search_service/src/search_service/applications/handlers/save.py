"""SaveHandler: сохранение постов, дедуп, нормализация VK URL."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from search_service.applications.ports.collector_client import RawPost
from search_service.applications.ports.uow import UnitOfWork
from search_service.domain.entities import Publication, Search, SearchResult, SearchTarget
from search_service.domain.enums import DateStatus


def make_title(title: str | None, text: str) -> tuple[str, str]:
    if title:
        return title, "title"
    text = text.strip()
    if len(text) <= 120:
        return text, "post_start"
    cut = text[:120]
    last_space = cut.rfind(" ")
    if last_space > 60:
        cut = cut[:last_space]
    return cut + "…", "post_start"


def normalize_vk_post(url: str) -> tuple[str, str, str]:
    """Нормализует VK URL: vk.ru/m.vk.com/?w=wall → (vk, owner_id, post_id)."""
    url = url.lower().strip().replace("vk.ru", "vk.com").replace("m.vk.com", "vk.com")
    match = re.search(r"wall(-?\d+)_(\d+)", url)
    if match:
        return "vk", match.group(1), match.group(2)
    parsed = urlparse(url)
    return "vk", parsed.netloc, parsed.path


def normalize_post_key(
    platform: str, source_external_id: str, post_external_id: str, url: str
) -> tuple[str, str, str]:
    """Применяет нормализацию только для VK."""
    if platform == "vk":
        return normalize_vk_post(url)
    return platform, source_external_id, post_external_id


class SaveHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def save_posts(
        self, search: Search, target: SearchTarget, posts: list[RawPost]
    ) -> list[SearchResult]:
        async with self.uow:
            source_cache: dict[tuple[str, str], object] = {}
            results: list[SearchResult] = []

            for post in posts:
                norm_platform, norm_source_id, norm_post_id = normalize_post_key(
                    post.platform, post.source_external_id, post.post_external_id, post.url
                )

                existing_pub = await self.uow.publications.get_by_key(
                    norm_platform, norm_source_id, norm_post_id
                )

                if existing_pub:
                    pub = existing_pub
                    pub.text = post.text
                    pub.metrics = post.metrics or pub.metrics
                    pub.title = post.title or pub.title
                    pub.source_name = post.source_name
                    pub.source_url = post.source_url
                    pub.url = post.url
                    pub.published_at = post.published_at or pub.published_at
                    pub.last_seen_at = datetime.now(timezone.utc)
                    await self.uow.publications.upsert(pub)
                else:
                    pub = Publication(
                        platform=norm_platform,
                        source_external_id=norm_source_id,
                        post_external_id=norm_post_id,
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
                    await self.uow.publications.upsert(pub)

                exists_in_search = await self.uow.results.exists_in_search(
                    search.id, pub.id
                )
                if exists_in_search:
                    continue

                if post.published_at is None:
                    date_status = DateStatus.UNKNOWN
                elif search.period.contains(post.published_at):
                    date_status = DateStatus.IN_PERIOD
                else:
                    continue

                src_key = (norm_platform, norm_source_id)
                if src_key not in source_cache:
                    source_cache[src_key] = await self.uow.sources.get_by_key(*src_key)
                source = source_cache[src_key]
                region_by_source = bool(source and getattr(source, "is_regional", False))

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