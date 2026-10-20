"""Заглушка коллектора: реализует порт CollectorClient без сети.

Включается явно (COLLECTOR_MODE=stub) для офлайн-разработки: пайплайн, дедуп, скоринг-стаб
и экспорт работают end-to-end на фикстурах. Переключение на боевой
клиент — COLLECTOR_MODE=grpc (по умолчанию), хэндлеры не меняются.
Имитация должна быть помечена (warning у поиска + README).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from search_service.applications.ports.collector_client import (
    CollectResult,
    RawPost,
    SourceInfo,
)
from search_service.domain.enums import Platform
from search_service.domain.errors import CollectorError

log = structlog.get_logger()

_URL_PLATFORMS = (("vk.com", "vk"), ("ok.ru", "ok"), ("odnoklassniki.ru", "ok"), ("max.ru", "max"))

# platform, source_external_id, source_name, post_external_id, days_ago, title, text, ...
_FIXTURES: list[dict[str, Any]] = [
    dict(
        platform="vk",
        source_external_id="krsk_news",
        source_name="Красноярск: главное",
        post_external_id="101",
        days_ago=2,
        title="ГИБДД: аварийность на дорогах края снизилась на 12% с начала года",
        text="В Красноярском крае ГИБДД подвела итоги полугодия: число ДТП снизилось на 12% "
        "к аналогичному периоду прошлого года. В ведомстве связывают это с кампанией "
        "«Безопасные качественные дороги» и новыми комплексами фотовидеофиксации. "
        "В Красноярске у школ оборудуют дополнительные освещённые пешеходные переходы.",
        metrics={"views": 5400, "likes": 31, "reposts": 7, "comments": 4},
    ),
    dict(
        platform="vk",
        source_external_id="krsk_auto",
        source_name="Авто Красноярск",
        post_external_id="205",
        days_ago=1,
        title=None,
        text="В Красноярском крае ГИБДД подвела итоги полугодия: число ДТП снизилось на 12% "
        "к аналогичному периоду прошлого года. В ведомстве связывают это с кампанией "
        "«Безопасные качественные дороги» и новыми комплексами фотовидеофиксации. "
        "В Красноярске у школ оборудуют дополнительные освещённые пешеходные переходы.",
        metrics={"views": 900, "likes": 4, "reposts": 0, "comments": 1},
        is_repost=True,
        repost_of_url="https://vk.com/wall-2034_101",
    ),
    dict(
        platform="ok",
        source_external_id="ok_krsk",
        source_name="Одноклассники: Красноярск",
        post_external_id="301",
        days_ago=5,
        title=None,
        text="Аварийность на дорогах края с начала года минус 12%. ГИБДД объясняет кампанией "
        "«Безопасные качественные дороги» и новыми камерами в Красноярске. "
        "У школ обещают освещённые переходы.",
        metrics={"views": 1200, "likes": 9, "reposts": 2, "comments": 0},
    ),
    dict(
        platform="max",
        source_external_id="max_krsk",
        source_name="MAX: край",
        post_external_id="401",
        days_ago=1,
        title="У школ Красноярска появятся освещённые пешеходные переходы",
        text="В Красноярске у школ оборудуют освещённые пешеходные переходы, сообщили в ГИБДД "
        "края. Мера входит в кампанию «Безопасные качественные дороги»: с начала года "
        "аварийность в регионе снизилась на 12%.",
        metrics={"views": 300, "likes": 2, "reposts": 0, "comments": 0},
    ),
    dict(
        platform="vk",
        source_external_id="krsk_news",
        source_name="Красноярск: главное",
        post_external_id="102",
        days_ago=3,
        title="Пожарная безопасность: жителям напомнили правила обращения с обогревателями",
        text="В Красноярском крае МЧС напомнило жителям правила пожарной безопасности при "
        "использовании обогревательных приборов. Инспекторы просят не оставлять технику "
        "без присмотра и проверить проводку перед сезоном.",
        metrics={"views": 2100, "likes": 6, "reposts": 1, "comments": 0},
    ),
    dict(
        platform="ok",
        source_external_id="ok_krsk",
        source_name="Одноклассники: Красноярск",
        post_external_id="302",
        days_ago=None,
        title=None,
        text="Читатели сообщают: у школы на улице Мира месяц не работает пешеходный переход. "
        "Родители просят мэрию восстановить освещение и разметку к началу учебного года.",
        metrics={"views": 450, "likes": 3, "reposts": 0, "comments": 2},
    ),
]


class StubCollectorClient:
    is_stub = True  # пайплайн по этому флагу добавляет warning «имитация»

    def __init__(self, fail_platforms: tuple[str, ...] = (), latency_s: float = 0.2):
        self._fail = set(fail_platforms)
        self._latency = latency_s

    async def resolve_source(self, url: str) -> SourceInfo:
        platform = next((p for host, p in _URL_PLATFORMS if host in url), None)
        if platform is None:
            raise CollectorError("UNSUPPORTED_URL")
        screen = url.rstrip("/").rsplit("/", 1)[-1]
        if screen == "missing":
            raise CollectorError("SOURCE_NOT_FOUND")
        return SourceInfo(
            platform=platform,
            external_id=screen,
            screen_name=screen,
            url=url,
            name=f"«{screen}» (имитация)",
            city="Красноярск",
            members_count=10_000,
            is_closed="closed" in screen,
        )

    async def collect_from_source(
        self,
        *,
        platform: str,
        source_external_id: str,
        start_utc: datetime,
        end_utc: datetime,
        keywords: list[str],
        max_posts: int = 300,
    ) -> CollectResult:
        await asyncio.sleep(self._latency)
        self._raise_if_down(platform)
        posts = [
            self._to_raw(p)
            for p in _FIXTURES
            if p["platform"] == platform and p["source_external_id"] == source_external_id
        ]
        return self._pack(posts, start_utc, end_utc, max_posts)

    async def search_platform(
        self,
        *,
        platform: str,
        queries: list[str],
        start_utc: datetime,
        end_utc: datetime,
        region_terms: list[str],
        max_posts: int = 500,
    ) -> CollectResult:
        await asyncio.sleep(self._latency)
        self._raise_if_down(platform)
        posts = [self._to_raw(p) for p in _FIXTURES if p["platform"] == platform]
        return self._pack(posts, start_utc, end_utc, max_posts)

    async def global_platforms(self) -> set[str]:
        return {p.value for p in Platform} - set(self._fail)

    def _raise_if_down(self, platform: str) -> None:
        if platform in self._fail:
            raise CollectorError("PLATFORM_UNAVAILABLE", f"{platform} недоступна (имитация)")

    def _pack(
        self, posts: list[RawPost], start_utc: datetime, end_utc: datetime, max_posts: int
    ) -> CollectResult:
        posts = [
            p for p in posts if p.published_at is None or start_utc <= p.published_at <= end_utc
        ]
        log.info("stub collect", n=len(posts))
        return CollectResult(posts=posts[:max_posts], truncated=len(posts) > max_posts, warnings=())

    @staticmethod
    def _to_raw(p: dict[str, Any]) -> RawPost:
        published = (
            datetime.now(UTC) - timedelta(days=p["days_ago"]) if p["days_ago"] is not None else None
        )
        return RawPost(
            platform=p["platform"],
            source_external_id=p["source_external_id"],
            post_external_id=p["post_external_id"],
            url=f"https://{p['platform']}.com/wall_{p['post_external_id']}",
            source_name=p["source_name"],
            source_url=f"https://{p['platform']}.com/{p['source_external_id']}",
            text=p["text"],
            title=p.get("title"),
            published_at=published,
            metrics=p.get("metrics"),
            is_repost=p.get("is_repost", False),
            repost_of_url=p.get("repost_of_url"),
        )
