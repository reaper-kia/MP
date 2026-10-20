"""Внутренние типы сервиса. Коннекторы работают только с ними, proto — только в transport/."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from collector_service.domain.enums import Health, Platform


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Period:
    """Границы включительно, aware-datetime в UTC."""

    start: datetime
    end: datetime

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment <= self.end


@dataclass(frozen=True, slots=True)
class PlatformInfo:
    platform: Platform
    title: str
    source_mode_supported: bool
    global_mode_supported: bool
    health: Health
    note: str = ""


@dataclass(frozen=True, slots=True)
class SourceInfo:
    platform: Platform
    external_id: str
    screen_name: str
    url: str
    name: str
    city: str | None = None
    members_count: int | None = None
    is_closed: bool = False


@dataclass(frozen=True, slots=True)
class PostMetrics:
    views: int | None = None
    likes: int | None = None
    reposts: int | None = None
    comments: int | None = None


@dataclass(frozen=True, slots=True)
class RawPost:
    """Пост ровно как на площадке. Нет данных — None, никаких подстановок."""

    platform: Platform
    source_external_id: str
    source_name: str
    source_url: str
    post_external_id: str
    url: str
    text: str
    title: str | None = None
    published_at: datetime | None = None
    metrics: PostMetrics = field(default_factory=PostMetrics)
    is_repost: bool = False
    repost_of_url: str | None = None
    fetched_at: datetime = field(default_factory=utc_now)

    @property
    def key(self) -> tuple[Platform, str, str]:
        """Ключ уникальности размещения (ARCHITECTURE §5)."""
        return self.platform, self.source_external_id, self.post_external_id


@dataclass(slots=True)
class CollectResult:
    posts: list[RawPost] = field(default_factory=list)
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
    # False — сбор оборвался (кончился бюджет времени, площадка упала посреди сбора): такой
    # ответ отдаём, но не кэшируем. Обрезка по max_posts — полный ответ (B2-20)
    complete: bool = True


@dataclass(frozen=True, slots=True)
class Page:
    """Порция постов от коннектора. Сбор идёт потоком страниц: потребитель может остановиться
    в любой момент (лимит постов, бюджет времени), и площадку больше не дёргаем.

    truncated — площадка сама перестала отдавать (предел глубины), хотя посты за период ещё есть.
    """

    posts: list[RawPost] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False
