from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from search_service.applications.ports.uow import UnitOfWork
from search_service.applications.ports.collector_client import RawPost
from search_service.domain.entities import Publication, SearchResult, Search, SearchTarget
from search_service.domain.enums import DateStatus


def make_title(post: RawPost) -> tuple[str, str]:
    """Возвращает (title, title_source). Если заголовка нет, берёт начало текста."""
    if post.title:
        return post.title, "title"
    text = post.text.strip()
    if len(text) <= 120:
        return text, "post_start"
    # Обрезаем по границе слова
    cut = text[:120]
    last_space = cut.rfind(" ")
    if last_space > 60:
        cut = cut[:last_space]
    return cut + "…", "post_start"


def normalize_vk_post(url: str) -> tuple[str, str, str]:
    """
    Нормализует VK URL к единому виду для дедупликации.
    Преобразует vk.ru, m.vk.com, ?w=wall-123_45 в platform='vk', source_id='-123', post_id='45'
    """
    url = url.lower().strip()
    url = url.replace('vk.ru', 'vk.com').replace('m.vk.com', 'vk.com')
    
    # Ищем паттерн wall-OwnerID_PostID (OwnerID может быть с минусом для групп)
    match = re.search(r'wall(-?\d+)_(\d+)', url)
    if match:
        return "vk", match.group(1), match.group(2)
    
    # Fallback: если паттерн не найден, берём домен и путь
    parsed = urlparse(url)
    return "vk", parsed.netloc, parsed.path


def normalize_post_key(platform: str, source_external_id: str, post_external_id: str, url: str) -> tuple[str, str, str]:
    """Применяет нормализацию только для VK, для остальных возвращает как есть."""
    if platform == "vk":
        p, s, post = normalize_vk_post(url)
        return p, s, post
    return platform, source_external_id, post_external_id


class SaveHandler:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def save_posts(self, search: Search, target: SearchTarget, posts: list[RawPost]) -> list[SearchResult]:
        """
        Upsert публикаций + дедупликация на уровне поиска.
        Возвращает список созданных SearchResult.
        """
        async with self.uow:
            source_cache: dict[tuple[str, str], object] = {}
            results: list[SearchResult] = []
            
            for post in posts:
                # 1. Нормализация ключа (B2-18)
                norm_platform, norm_source_id, norm_post_id = normalize_post_key(
                    post.platform, post.source_external_id, post.post_external_id, post.url
                )
                
                # 2. Проверка существующей публикации (Upsert логика)
                existing_pub = await self.uow.publications.get_by_key(norm_platform, norm_source_id, norm_post_id)
                
                if existing_pub:
                    pub = existing_pub
                    # Обновляем данные, если пост пришёл снова (например, с новыми метриками или из другого источника)
                    pub.text = post.text
                    pub.metrics = post.metrics or pub.metrics
                    pub.title = post.title or pub.title
                    pub.source_name = post.source_name
                    pub.source_url = post.source_url
                    pub.url = post.url
                    pub.published_at = post.published_at or pub.published_at
                    pub.last_seen_at = datetime.now(timezone.utc)
                    await self.uow.publications.save(pub)
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

                # 3. Дедупликация на уровне конкретного поиска (B2-05)
                exists_in_search = await self.uow.results.exists_in_search(search.id, pub.id)
                if exists_in_search:
                    continue # Этот пост уже есть в этой подборке, не создаём дубль строки

                # 4. Проверка периода
                if post.published_at is None:
                    date_status = DateStatus.UNKNOWN
                elif search.period.contains(post.published_at):
                    date_status = DateStatus.IN_PERIOD
                else:
                    # Пост вне периода — не добавляем в результаты этого поиска
                    continue

                # 5. Определение региона по источнику
                src_key = (norm_platform, norm_source_id)
                if src_key not in source_cache:
                    source_cache[src_key] = await self.uow.sources.get_by_key(*src_key)
                source = source_cache[src_key]
                region_by_source = bool(source and getattr(source, 'is_regional', False))

                # 6. Создание записи в подборке
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