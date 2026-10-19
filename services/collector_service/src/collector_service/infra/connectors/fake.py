"""Тестовая площадка для разработки (COLLECTOR_FAKE=true). На демо выключена.

Каждый пост помечен «[FAKE]» в тексте и note площадки — спутать с настоящими нельзя.
Детерминирован: один и тот же источник за один и тот же период даёт те же посты
(значит, повторный сбор не плодит новые записи — так B2 может проверить дедуп).

Особые external_id для отладки сценария 5:
  "fail"   → PlatformUnavailableError
  "empty"  → источник без постов
  "closed" → SourcePrivateError
"""

import asyncio
import hashlib
from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timedelta

from collector_service.domain.enums import Health, Platform
from collector_service.domain.exceptions import (
    PlatformUnavailableError,
    SourcePrivateError,
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

HOSTS: dict[Platform, tuple[str, ...]] = {
    Platform.VK: ("vk.com", "vk.ru"),
    Platform.OK: ("ok.ru",),
    Platform.MAX: ("max.ru",),
    Platform.NEWS: ("example-news.ru",),
}
TITLES = {
    Platform.VK: "ВКонтакте",
    Platform.OK: "Одноклассники",
    Platform.MAX: "MAX",
    Platform.NEWS: "Новостные сайты",
}
TEXTS = (
    "[FAKE] В Ачинске сотрудники Госавтоинспекции провели рейд «Пешеход» у школ.",
    "[FAKE] На трассе Р-255 под Красноярском произошло ДТП с участием двух грузовиков.",
    "[FAKE] В Канске прошли учения МЧС по пожарной безопасности в торговых центрах.",
    "[FAKE] В Красноярске открыли новый пешеходный переход со светофором на ул. Ленина.",
    "[FAKE] Норильские школьники заняли призовые места на краевой олимпиаде.",
)


class FakeConnector:
    def __init__(self, platform: Platform, delay_seconds: float = 0.5) -> None:
        self.platform = platform
        self.title = TITLES[platform]
        self.hosts = HOSTS[platform]
        self._delay = delay_seconds

    async def health(self) -> PlatformInfo:
        return PlatformInfo(
            platform=self.platform,
            title=self.title,
            source_mode_supported=True,
            global_mode_supported=self.platform is not Platform.NEWS,
            health=Health.DEGRADED,
            note="ТЕСТОВЫЕ ДАННЫЕ (COLLECTOR_FAKE=true)",
        )

    async def resolve(self, url: str) -> SourceInfo:
        parts = path_parts(url)
        if not parts:
            raise UnsupportedUrlError("Нет имени группы в ссылке")
        handle = parts[-1]
        if handle == "closed":
            raise SourcePrivateError("Группа закрыта")
        return SourceInfo(
            platform=self.platform,
            external_id=handle,
            screen_name=handle,
            url=self._source_url(handle),
            name=f"[FAKE] {handle}",
            city="Красноярск",
            members_count=1000 + _num(handle) % 100_000,
        )

    async def collect(
        self,
        source_external_id: str,
        period: Period,
        keywords: Sequence[str],
    ) -> AsyncIterator[Page]:
        await asyncio.sleep(self._delay)
        if source_external_id == "fail":
            raise PlatformUnavailableError(f"{self.title}: тестовая ошибка источника")
        if source_external_id == "closed":
            raise SourcePrivateError("Группа закрыта")
        if source_external_id == "empty":
            return
        # период, обрезку до max_posts и truncated делает потребитель (applications/collecting.py):
        # коннектор отдаёт всё
        yield Page(posts=self._posts(source_external_id, period))

    async def search(
        self,
        queries: Sequence[str],
        period: Period,
        region_terms: Sequence[str],
    ) -> AsyncIterator[Page]:
        await asyncio.sleep(self._delay)
        for owner in ("fake_city_news", "fake_region_today"):
            yield Page(posts=self._posts(owner, period), warnings=["Тестовые данные"])

    def _posts(self, owner: str, period: Period) -> list[RawPost]:
        """Посты источника: первый — ровно на начале периода (проверка «включительно»),
        последний — без даты (UNKNOWN), плюс один пост вне периода — сервис обязан его отбросить."""
        span = period.end - period.start
        posts: list[RawPost] = []
        for i, text in enumerate(TEXTS):
            if i == 0:
                published: datetime | None = period.start
            elif i == len(TEXTS) - 1:
                published = None
            else:
                published = period.start + span * (i / len(TEXTS))
            posts.append(self._post(owner, str(i + 1), text, published, views=100 * (i + 1)))
        old = period.start - timedelta(days=1)
        posts.append(self._post(owner, "old", "[FAKE] Старый пост вне периода", old, views=None))
        return posts

    def _post(
        self, owner: str, post_id: str, text: str, published: datetime | None, views: int | None
    ) -> RawPost:
        source_url = self._source_url(owner)
        return RawPost(
            platform=self.platform,
            source_external_id=owner,
            source_name=f"[FAKE] {owner}",
            source_url=source_url,
            post_external_id=post_id,
            url=f"{source_url}/post/{post_id}",
            text=text,
            published_at=published,
            metrics=PostMetrics(views=views),
        )

    def _source_url(self, handle: str) -> str:
        return f"https://{self.hosts[0]}/{handle}"


def _num(value: str) -> int:
    return int(hashlib.sha1(value.encode()).hexdigest()[:8], 16)
