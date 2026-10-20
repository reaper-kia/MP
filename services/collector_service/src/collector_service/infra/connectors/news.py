"""Новостные сайты из перечня агентства через RSS (B1-08, P1).

resolve  → сайт из перечня по хосту ссылки (карточка = название из настроек / ленты)
collect  → RSS-лента сайта: элементы за период; если в ленте только анонс — открываем статью
           и берём текст со страницы (не вышло — остаётся анонс из ленты)
search   → свежие ленты всех сайтов перечня, отбор элементов по словам фраз. Это не поиск по
           архиву сайта: RSS отдаёт последние 20–100 материалов — так и пишем в warnings.

Источник = сайт: source_external_id — хост, post_external_id — путь статьи.
"""

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator, Callable, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from collector_service.domain.enums import Health, Platform
from collector_service.domain.exceptions import (
    CollectorError,
    PlatformUnavailableError,
    SourceNotFoundError,
    UnsupportedUrlError,
)
from collector_service.domain.urls import host_of
from collector_service.domain.value_objects import (
    Page,
    Period,
    PlatformInfo,
    RawPost,
    SourceInfo,
)
from collector_service.infra.cache import HealthCache
from collector_service.infra.news.rss import Feed, FeedError, FeedItem, parse_feed
from collector_service.infra.news.sites import NewsSite
from collector_service.infra.web.fetcher import WebFetcher
from collector_service.infra.web.html import article_text

logger = logging.getLogger(__name__)

PAGE_SIZE = 5  # статей на страницу потока: между ними потребитель может остановиться
SHORT_TEXT = 400  # короче — похоже на анонс, открываем статью
_WORD = re.compile(r"[0-9a-zа-яё]+", re.IGNORECASE)


class NewsConnector:
    platform = Platform.NEWS
    title = "Новостные сайты"

    def __init__(
        self,
        sites: Sequence[NewsSite],
        fetcher: WebFetcher,
        *,
        open_articles: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sites = {s.host: s for s in sites}
        self._fetcher = fetcher
        self._open_articles = open_articles
        self._health = HealthCache(clock)
        self.hosts: tuple[str, ...] = tuple(self._sites)

    # ---------- health ----------

    async def health(self) -> PlatformInfo:
        return await self._health.get(self._check_health)

    async def _check_health(self) -> PlatformInfo:
        if not self._sites:
            return self._info(Health.UNAVAILABLE, "Не задан перечень сайтов (NEWS_SITES)")
        results = await asyncio.gather(
            *(self._feed(site) for site in self._sites.values()), return_exceptions=True
        )
        broken = sum(isinstance(r, BaseException) for r in results)
        if broken == len(results):
            return self._info(Health.UNAVAILABLE, "Ни одна RSS-лента сайтов не открылась")
        note = (
            f"RSS-ленты {len(results) - broken} из {len(results)} сайтов; только свежие материалы"
        )
        return self._info(Health.DEGRADED if broken else Health.OK, note)

    def _info(self, health: Health, note: str) -> PlatformInfo:
        working = health is not Health.UNAVAILABLE
        return PlatformInfo(
            platform=self.platform,
            title=self.title,
            source_mode_supported=working,
            global_mode_supported=working,
            health=health,
            note=note,
        )

    # ---------- resolve ----------

    async def resolve(self, url: str) -> SourceInfo:
        site = self._site(host_of(url))
        feed = await self._feed(site)
        return SourceInfo(
            platform=self.platform,
            external_id=site.host,
            screen_name=site.host,
            url=f"https://{site.host}",
            name=site.name if site.name != site.host else (feed.title or site.host),
        )

    # ---------- collect ----------

    async def collect(
        self, source_external_id: str, period: Period, keywords: Sequence[str]
    ) -> AsyncIterator[Page]:
        site = self._site(source_external_id)
        feed = await self._feed(site)
        items = [i for i in feed.items if i.published_at is None or period.contains(i.published_at)]
        async for page in self._pages(site, items):
            yield page

    # ---------- search ----------

    async def search(
        self, queries: Sequence[str], period: Period, region_terms: Sequence[str]
    ) -> AsyncIterator[Page]:
        if not self._sites:
            raise PlatformUnavailableError(
                "Новостные сайты: перечень сайтов не настроен — обратитесь к администратору",
                detail="NEWS_SITES пуст",
            )
        matchers = [m for q in queries if (m := _Matcher.of(q)) is not None]
        sites = list(self._sites.values())
        feeds = await asyncio.gather(*(self._feed(s) for s in sites), return_exceptions=True)
        failed = [s.name for s, f in zip(sites, feeds, strict=True) if isinstance(f, BaseException)]
        if len(failed) == len(sites):
            raise PlatformUnavailableError(
                "Новостные сайты: ни один сайт не ответил, повторите позже",
                detail="ни одна RSS-лента не открылась: " + ", ".join(failed),
            )
        warnings = [
            f"Новостные сайты: поиск по свежим RSS-лентам {len(sites)} сайтов, не по архиву"
        ]
        if failed:
            warnings.append(f"Не открылись ленты сайтов: {', '.join(failed)}")
        yield Page(warnings=warnings)
        for site, feed in zip(sites, feeds, strict=True):
            if isinstance(feed, BaseException):
                continue
            items = [
                i
                for i in feed.items
                if (i.published_at is None or period.contains(i.published_at))
                and any(m.matches(f"{i.title} {i.text}") for m in matchers)
            ]
            async for page in self._pages(site, items):
                yield page

    # ---------- общее ----------

    async def _pages(self, site: NewsSite, items: list[FeedItem]) -> AsyncIterator[Page]:
        for start in range(0, len(items), PAGE_SIZE):
            chunk = items[start : start + PAGE_SIZE]
            posts = await asyncio.gather(*(self._post(site, item) for item in chunk))
            yield Page(posts=list(posts))

    async def _post(self, site: NewsSite, item: FeedItem) -> RawPost:
        text = item.text
        if self._open_articles and not item.full_text and len(text) < SHORT_TEXT:
            try:
                page = await self._fetcher.get(item.link, what=site.name)
                text = article_text(page.text) or text
            except CollectorError as exc:
                logger.info("news %s: статья не открылась (%s), берём анонс", site.host, exc)
        url = canonical_url(item.link)
        return RawPost(
            platform=self.platform,
            source_external_id=site.host,
            source_name=site.name,
            source_url=f"https://{site.host}",
            post_external_id=urlsplit(url).path.rstrip("/") or item.guid,
            url=url,
            title=item.title or None,
            text=text,
            published_at=item.published_at,
        )

    def _site(self, host: str) -> NewsSite:
        site = self._sites.get(host.lower().removeprefix("www."))
        if site is None:
            raise UnsupportedUrlError("Этого сайта нет в перечне новостных сайтов")
        return site

    async def _feed(self, site: NewsSite) -> Feed:
        page = await self._fetcher.get(site.feed_url, what=site.name)
        try:
            return parse_feed(page.text.encode())
        except FeedError as exc:
            raise SourceNotFoundError(
                f"{site.name}: не удалось прочитать ленту новостей сайта",
                detail=f"{site.feed_url}: RSS не разобралась ({exc})",
            ) from None


def canonical_url(link: str) -> str:
    """Ссылка из ленты без utm-меток и якоря: та же статья — та же ссылка."""
    parts = urlsplit(link.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")]
    host = parts.netloc.lower()
    return urlunsplit(("https", host, parts.path, urlencode(query), ""))


class _Matcher:
    """Грубый отбор «статья про это»: большинство слов фразы (по основе) есть в тексте.

    Смысл оценивает ML; здесь только чтобы не отдавать всю ленту на каждый запрос.
    """

    def __init__(self, stems: list[str]) -> None:
        self._stems = stems
        self._need = max(1, (len(stems) + 1) // 2)

    @classmethod
    def of(cls, phrase: str) -> "_Matcher | None":
        stems = [_stem(w) for w in _WORD.findall(phrase.lower()) if len(w) >= 3]
        return cls(stems) if stems else None

    def matches(self, text: str) -> bool:
        words = {_stem(w) for w in _WORD.findall(text.lower())}
        prefixes = {w[:6] for w in words}
        return sum(s in words or s[:6] in prefixes for s in self._stems) >= self._need


def _stem(word: str) -> str:
    return word if len(word) <= 4 else word[: max(4, len(word) - 2)]
