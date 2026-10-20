"""Одноклассники через публичные страницы ok.ru, без логина и без API (B1-04, B1-01).

Почему не API: в OK API нет метода «посты группы», а нужные права (VALUABLE_ACCESS) выдаются
по письму в поддержку — см. docs/collector-spike.md.

resolve  → GET ссылки группы: id из <link rel=canonical> (https://ok.ru/group/{gid}), название — h1
collect  → GET /group/{gid}/topics (20 топиков), дальше — POST подгрузки ленты (как делает
           сама страница: st.page + st.lastelem из div.loader-container), пока топики не станут
           старше начала периода
read_post→ GET страницы топика — для поиска «везде» через Яндекс (connectors/site_search.py)

Ссылка на пост каноничная: https://ok.ru/group/{gid}/topic/{tid}. Время на страницах — московское
(infra/ok/dates.py). title не заполняем (B1-04). Лимит — ok_requests_per_second на хост ok.ru.
"""

import time
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime
from urllib.parse import urlencode

from collector_service.domain import messages
from collector_service.domain.enums import Health, Platform
from collector_service.domain.exceptions import (
    CollectorError,
    RateLimitedError,
    SourceNotFoundError,
    UnsupportedUrlError,
)
from collector_service.domain.urls import path_parts
from collector_service.domain.value_objects import (
    Page,
    Period,
    PlatformInfo,
    PostMetrics,
    RawPost,
    SourceInfo,
)
from collector_service.infra.cache import HealthCache
from collector_service.infra.ok.pages import (
    OkTopic,
    group_url,
    is_topic_url,
    parse_group,
    parse_topic_page,
    parse_topics_page,
)
from collector_service.infra.web.fetcher import WebFetcher

FEED_PAGE_SIZE = 20  # столько топиков OK отдаёт на страницу ленты
FEED_MAX_PAGES = 40  # → до 800 топиков
NOT_GROUP = frozenset({"profile", "dk", "search", "video", "music", "games", "app", "feed"})
HEALTH_URL = "https://ok.ru/ngs24"


class OkConnector:
    platform = Platform.OK
    title = "Одноклассники"
    hosts: tuple[str, ...] = ("ok.ru",)

    def __init__(
        self,
        fetcher: WebFetcher,
        *,
        health_url: str = HEALTH_URL,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._web = fetcher
        self._health_url = health_url
        self._now = now
        self._health = HealthCache(clock)

    # ---------- health ----------

    async def health(self) -> PlatformInfo:
        return await self._health.get(self._check_health)

    async def _check_health(self) -> PlatformInfo:
        try:
            page = await self._web.get(self._health_url, what=self.title)
        except RateLimitedError:
            return self._info(Health.DEGRADED, "Одноклассники ограничивают частоту запросов")
        except CollectorError as exc:
            return self._info(Health.UNAVAILABLE, str(exc))
        if parse_group(page.text) is None:
            return self._info(Health.DEGRADED, "Одноклассники: страница группы изменилась")
        return self._info(Health.OK, "Публичные страницы групп, без логина")

    def _info(self, health: Health, note: str) -> PlatformInfo:
        working = health is not Health.UNAVAILABLE
        return PlatformInfo(
            platform=self.platform,
            title=self.title,
            source_mode_supported=working,
            global_mode_supported=False,  # «везде» подключает WithSiteSearch (Яндекс)
            health=health,
            note=note,
        )

    # ---------- resolve ----------

    async def resolve(self, url: str) -> SourceInfo:
        parts = path_parts(url)
        if not parts or parts[0] in NOT_GROUP:
            raise UnsupportedUrlError("Ожидается ссылка на группу: ok.ru/имя или ok.ru/group/123")
        if parts[0] == "group":
            if len(parts) < 2 or not parts[1].isdigit():
                raise UnsupportedUrlError("Ожидается ссылка вида ok.ru/group/123")
            page_url, screen_name = group_url(parts[1]), f"group/{parts[1]}"
        else:
            page_url, screen_name = f"https://ok.ru/{parts[0]}", parts[0]
        page = await self._web.get(page_url, what=self.title)
        group = parse_group(page.text)
        if group is None:
            if "/profile/" in page.url:
                raise UnsupportedUrlError("Это страница человека, а не группы в Одноклассниках")
            raise SourceNotFoundError("Группа не найдена в Одноклассниках")
        return SourceInfo(
            platform=self.platform,
            external_id=group.gid,
            screen_name=screen_name,
            url=group.url,
            name=group.name,
        )

    # ---------- collect ----------

    async def collect(
        self, source_external_id: str, period: Period, keywords: Sequence[str]
    ) -> AsyncIterator[Page]:
        gid = source_external_id.strip()
        if not gid.isdigit():
            raise UnsupportedUrlError(
                messages.source_not_found(self.title), detail=f"OK: некорректный id группы {gid!r}"
            )
        topics_url = f"{group_url(gid)}/topics"
        first = await self._web.get(topics_url, what=self.title)
        if parse_group(first.text) is None and "groups_post" not in first.text:
            raise SourceNotFoundError("Группа не найдена в Одноклассниках или закрыта")
        parsed = parse_topics_page(first.text, self._now())
        cursor = parsed.cursor
        seen: set[str] = set()
        for page_number in range(1, FEED_MAX_PAGES + 1):
            fresh = [t for t in parsed.topics if t.tid not in seen]
            seen.update(t.tid for t in fresh)
            if fresh:
                yield Page(posts=[self._post(t) for t in fresh])
            if _reached_start(fresh, period):
                return
            if page_number > 1 and not fresh:
                yield _stopped(page_number)  # следующая страница ничего нового не дала
                return
            if cursor is None:
                if len(fresh) >= FEED_PAGE_SIZE:  # страница полная, а листать нечем
                    yield _stopped(page_number)
                return
            response = await self._web.post(
                f"{cursor.url}&"
                + urlencode({"st.page": page_number + 1, "st.lastelem": cursor.last_element}),
                data={"fetch": "false"},
                headers={"X-Requested-With": "XMLHttpRequest", "Referer": topics_url},
                what=self.title,
            )
            parsed = parse_topics_page(response.text, self._now())
            # страница со своим курсором — дальше листаем по нему, иначе по прежнему
            cursor = parsed.cursor or cursor
        yield Page(
            truncated=True,
            warnings=["Одноклассники: достигнут предел глубины ленты — старые посты не проверены"],
        )

    # ---------- search: «везде» подключается снаружи (WithSiteSearch) ----------

    async def search(
        self, queries: Sequence[str], period: Period, region_terms: Sequence[str]
    ) -> AsyncIterator[Page]:
        raise UnsupportedUrlError("Поиск по всем Одноклассникам — только через Яндекс")
        yield Page()  # pragma: no cover

    # ---------- PostReader ----------

    def accepts(self, url: str) -> bool:
        return is_topic_url(url.replace("http://", "https://", 1))

    async def read_post(self, url: str) -> RawPost | None:
        page = await self._web.get(url, what=self.title)
        topic = parse_topic_page(page.text, self._now())
        return self._post(topic) if topic is not None else None

    def _post(self, topic: OkTopic) -> RawPost:
        return RawPost(
            platform=self.platform,
            source_external_id=topic.gid,
            source_name=topic.group_name or f"group/{topic.gid}",
            source_url=group_url(topic.gid),
            post_external_id=topic.tid,
            url=topic.url,
            text=topic.text,
            published_at=topic.published_at,
            metrics=PostMetrics(likes=topic.likes, reposts=topic.reshares, comments=topic.comments),
        )


def _reached_start(topics: list[OkTopic], period: Period) -> bool:
    """Лента идёт от новых к старым: незакреплённый топик старше начала периода — дальше
    только старее. Топик без даты остановку не вызывает."""
    return any(
        t.published_at is not None and t.published_at < period.start and not t.pinned
        for t in topics
    )


def _stopped(pages: int) -> Page:
    return Page(
        truncated=True,
        warnings=[
            f"Одноклассники: лента группы дальше не листается (страниц: {pages}) — "
            "более старые посты периода могли не попасть"
        ],
    )
