"""Гарантии, одинаковые для любой площадки, — чтобы коннекторы не повторяли их.

- пустой текст: пост не возвращается;
- период: посты с датой вне периода отбрасываются, без даты — остаются (их пометит search);
- дубли по (platform, source_external_id, post_external_id) внутри ответа схлопываются;
- max_posts: лишнее обрезается, truncated=True.
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


def finalize_result(
    result: CollectResult, period: Period, limit: int
) -> tuple[CollectResult, FinalizeStats]:
    seen: set[tuple[Platform, str, str]] = set()
    posts: list[RawPost] = []
    empty = outside = 0
    for post in result.posts:
        if not post.text.strip():
            empty += 1
            continue
        if post.published_at is not None and not period.contains(post.published_at):
            outside += 1
            continue
        if post.key in seen:
            continue
        seen.add(post.key)
        posts.append(post)

    warnings = list(result.warnings)
    if empty:
        warnings.append(f"Пропущено постов без текста: {empty}")
    truncated = result.truncated or len(posts) > limit
    stats = FinalizeStats(
        received=len(result.posts),
        kept=min(len(posts), limit),
        empty_text=empty,
        outside_period=outside,
    )
    return CollectResult(posts=posts[:limit], truncated=truncated, warnings=warnings), stats
