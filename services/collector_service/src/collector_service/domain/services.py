"""Гарантии, одинаковые для любой площадки, — чтобы коннекторы не повторяли их.

- пустой текст: пост не возвращается;
- период: посты с датой вне периода отбрасываются, без даты — остаются (их пометит search);
- дубли по (platform, source_external_id, post_external_id) внутри ответа схлопываются;
- max_posts: лишнее обрезается, truncated=True.

PostAccumulator применяет их по мере прихода страниц (сбор идёт потоком и может остановиться
по лимиту или по времени), finalize_result — то же для готового списка.
"""

from dataclasses import dataclass

from collector_service.domain.enums import Platform
from collector_service.domain.value_objects import CollectResult, Period, RawPost


@dataclass(frozen=True, slots=True)
class FinalizeStats:
    """Сколько постов пришло, осталось и почему выкинули остальные (для логов, без текстов)."""

    received: int
    kept: int
    empty_text: int
    outside_period: int


class PostAccumulator:
    def __init__(self, period: Period, limit: int) -> None:
        self._period = period
        self._limit = limit
        self._seen: set[tuple[Platform, str, str]] = set()
        self._posts: list[RawPost] = []
        self._warnings: list[str] = []
        self._received = self._empty = self._outside = 0
        self.truncated = False
        self.complete = True  # False — сбор оборван по времени или ошибке (не кэшировать)

    @property
    def kept(self) -> int:
        return len(self._posts)

    def add(self, posts: list[RawPost]) -> None:
        for post in posts:
            self._received += 1
            if not post.text.strip():
                self._empty += 1
                continue
            if post.published_at is not None and not self._period.contains(post.published_at):
                self._outside += 1
                continue
            if post.key in self._seen:
                continue
            if len(self._posts) >= self._limit:
                self.truncated = True
                continue
            self._seen.add(post.key)
            self._posts.append(post)

    def warn(self, warning: str) -> None:
        if warning not in self._warnings:
            self._warnings.append(warning)

    def result(self) -> tuple[CollectResult, FinalizeStats]:
        warnings = list(self._warnings)
        if self._empty:
            warnings.append(f"Пропущено постов без текста: {self._empty}")
        stats = FinalizeStats(
            received=self._received,
            kept=len(self._posts),
            empty_text=self._empty,
            outside_period=self._outside,
        )
        return (
            CollectResult(
                posts=list(self._posts),
                truncated=self.truncated,
                warnings=warnings,
                complete=self.complete,
            ),
            stats,
        )


def finalize_result(
    result: CollectResult, period: Period, limit: int
) -> tuple[CollectResult, FinalizeStats]:
    acc = PostAccumulator(period, limit)
    acc.add(result.posts)
    for warning in result.warnings:
        acc.warn(warning)
    acc.truncated |= result.truncated
    acc.complete = result.complete
    return acc.result()
