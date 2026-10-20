"""Режим «везде» для площадок без своего поиска (OK, MAX): поисковик → открыть каждую ссылку.

VK свой поиск имеет (newsfeed.search), но токену пользователя VK ID он закрыт (ошибка 1051) —
тогда WithSearchFallback переключает VK на тот же путь: Яндекс site:vk.com → wall.getById.

Стратегия, а не часть коннектора: подключается к любой площадке, у которой есть PostReader
(умеет открыть пост по ссылке). Правило достоверности (B1-06): ссылка из выдачи попадает в
ответ, только если пост открылся и с его страницы получены текст и (если есть) дата.
Ссылки на группы, профили, каталоги отбрасываются ещё до открытия (PostReader.accepts).

Дату период не задаёт: API Яндекса умеет только «сутки / 2 недели / месяц», поэтому отбор по
периоду — после открытия страницы (это делает общий потребитель потока, collecting.py).
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from collector_service.applications.ports.connectors import PlatformConnector, PostReader
from collector_service.domain import messages
from collector_service.domain.exceptions import (
    CollectorError,
    MethodUnavailableError,
    PlatformUnavailableError,
    RateLimitedError,
    log_text,
)
from collector_service.domain.value_objects import Page, Period, PlatformInfo, RawPost, SourceInfo
from collector_service.infra.yandex_search.client import SearchHit, YandexSearchClient

logger = logging.getLogger(__name__)

COVERAGE_NOTE = "поиск через Яндекс — покрытие неполное"


@dataclass
class SiteSearch:
    client: YandexSearchClient
    site: str  # "ok.ru" → оператор site:ok.ru
    reader: PostReader
    pages_per_query: int = 1  # одна страница выдачи = до 100 ссылок = 1 платный запрос
    open_concurrency: int = 3

    @property
    def configured(self) -> bool:
        return self.client.configured

    async def search(self, queries: Sequence[str], period: Period) -> AsyncIterator[Page]:
        opened: set[str] = set()
        failures = skipped = 0
        first_error: CollectorError | None = None
        succeeded = 0
        for query in queries:
            try:
                hits = await self._hits(query)
            except CollectorError as exc:
                first_error = first_error or exc
                logger.warning("site_search %s: фраза не обработана: %s", self.site, log_text(exc))
                continue
            succeeded += 1
            urls: list[str] = []
            for hit in hits:
                if hit.url in opened:
                    continue
                if not self.reader.accepts(hit.url):
                    skipped += 1
                    continue
                opened.add(hit.url)
                urls.append(hit.url)
            posts, failed = await self._open(urls)
            failures += failed
            yield Page(posts=posts, warnings=[f"{self.site}: {COVERAGE_NOTE}"])
        if succeeded == 0 and first_error is not None:
            raise first_error
        tail: list[str] = []
        if failures:
            tail.append(f"{self.site}: не открылись ссылки из поиска ({failures}) — не включены")
        if tail:
            yield Page(warnings=tail)
        logger.info(
            "site_search %s: opened=%d failed=%d not_a_post=%d",
            self.site,
            len(opened),
            failures,
            skipped,
        )

    async def _hits(self, query: str) -> list[SearchHit]:
        text = f"{query} site:{self.site}"
        hits: list[SearchHit] = []
        for page in range(self.pages_per_query):
            batch = await self.client.search(text, page=page)
            hits.extend(batch)
            if not batch:
                break
        return hits

    async def _open(self, urls: list[str]) -> tuple[list[RawPost], int]:
        semaphore = asyncio.Semaphore(self.open_concurrency)

        async def one(url: str) -> RawPost | None:
            async with semaphore:
                return await self.reader.read_post(url)

        results = await asyncio.gather(*(one(u) for u in urls), return_exceptions=True)
        posts: list[RawPost] = []
        failed = 0
        for result in results:
            if isinstance(result, RateLimitedError):
                raise result  # площадка просит остановиться — не добиваем её дальше
            if isinstance(result, BaseException) or result is None:
                failed += 1
                continue
            posts.append(result)
        return posts, failed


class WithSiteSearch:
    """Декоратор коннектора: всё как у площадки, но режим «везде» — через SiteSearch."""

    def __init__(self, base: PlatformConnector, site_search: SiteSearch) -> None:
        self._base = base
        self._site_search = site_search
        self.platform = base.platform
        self.title = base.title
        self.hosts = base.hosts

    async def health(self) -> PlatformInfo:
        info = await self._base.health()
        if not info.source_mode_supported:
            return info
        if not self._site_search.configured:
            note = "Поиск по всей площадке — только через Yandex Search API (ключ не задан)"
            return _with(info, global_mode=False, note=note)
        return _with(info, global_mode=True, note=f"Поиск «везде»: {COVERAGE_NOTE}")

    async def resolve(self, url: str) -> SourceInfo:
        return await self._base.resolve(url)

    def collect(
        self, source_external_id: str, period: Period, keywords: Sequence[str]
    ) -> AsyncIterator[Page]:
        return self._base.collect(source_external_id, period, keywords)

    def search(
        self, queries: Sequence[str], period: Period, region_terms: Sequence[str]
    ) -> AsyncIterator[Page]:
        return self._site_search.search(queries, period)


class WithSearchFallback:
    """Декоратор коннектора со своим поиском: пока площадка ищет сама — её поиск; если метод поиска
    ключу закрыт (MethodUnavailableError) — дальше «везде» через SiteSearch, без повторных попыток.

    native=False — свой поиск площадки не пробуем вовсе (VK_NEWSFEED_SEARCH=false): заранее
    известно, что он закрыт, а пробная ошибка в первом поиске после старта только пугает.
    """

    def __init__(
        self, base: PlatformConnector, site_search: SiteSearch, *, native: bool = True
    ) -> None:
        self._base = base
        self._site_search = site_search
        self._native_closed = not native
        self.platform = base.platform
        self.title = base.title
        self.hosts = base.hosts

    async def health(self) -> PlatformInfo:
        info = await self._base.health()
        if not self._native_closed or not info.source_mode_supported:
            return info
        if not self._site_search.configured:
            note = "Поиск по всей площадке VK закрыт для ключа приложения (ошибка 1051)"
            return _with(info, global_mode=False, note=note)
        return _with(info, global_mode=True, note=self._fallback_note)

    @property
    def _fallback_note(self) -> str:
        """VK 1051 — не ошибка цели, а заметка площадки (B1-13)."""
        return f"{self.title}: {messages.VIA_YANDEX_NOTE}, {COVERAGE_NOTE}"

    async def resolve(self, url: str) -> SourceInfo:
        return await self._base.resolve(url)

    def collect(
        self, source_external_id: str, period: Period, keywords: Sequence[str]
    ) -> AsyncIterator[Page]:
        return self._base.collect(source_external_id, period, keywords)

    async def search(
        self, queries: Sequence[str], period: Period, region_terms: Sequence[str]
    ) -> AsyncIterator[Page]:
        if not self._native_closed:
            yielded = False
            try:
                async for page in self._base.search(queries, period, region_terms):
                    yielded = True
                    yield page
                return
            except MethodUnavailableError as exc:
                if yielded:
                    raise
                logger.warning(
                    "%s: свой поиск закрыт (%s) — дальше через Яндекс", self.title, log_text(exc)
                )
                self._native_closed = True
        if not self._site_search.configured:
            raise PlatformUnavailableError(
                messages.GLOBAL_SEARCH_NOT_CONFIGURED,
                detail=(
                    f"{self.title}: свой поиск закрыт для ключа (1051), "
                    "а YC_FOLDER_ID / YC_SEARCH_API_KEY не заданы"
                ),
            )
        first = True
        async for page in self._site_search.search(queries, period):
            if first:  # заметка — с первой страницей: упадёт Яндекс сразу — это ошибка цели
                first = False
                page = Page(
                    posts=page.posts,
                    warnings=[self._fallback_note, *page.warnings],
                    truncated=page.truncated,
                )
            yield page


def _with(info: PlatformInfo, *, global_mode: bool, note: str) -> PlatformInfo:
    joined = "; ".join(n for n in (info.note, note) if n)
    return PlatformInfo(
        platform=info.platform,
        title=info.title,
        source_mode_supported=info.source_mode_supported,
        global_mode_supported=global_mode,
        health=info.health,
        note=joined,
    )
