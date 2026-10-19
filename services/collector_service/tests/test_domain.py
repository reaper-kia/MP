"""Правила domain без коннекторов и Mediator: ссылки и общие гарантии по постам."""

from datetime import UTC, datetime, timedelta

import pytest

from collector_service.domain.enums import Platform
from collector_service.domain.exceptions import UnsupportedUrlError
from collector_service.domain.services import finalize_result
from collector_service.domain.urls import normalize_url
from collector_service.domain.value_objects import CollectResult, Period, RawPost

PERIOD = Period(
    start=datetime(2026, 10, 1, tzinfo=UTC),
    end=datetime(2026, 10, 19, 23, 59, 59, tzinfo=UTC),
)


def post(post_id: str, text: str = "Текст", published: datetime | None = PERIOD.start) -> RawPost:
    return RawPost(
        platform=Platform.VK,
        source_external_id="-1",
        source_name="Источник",
        source_url="https://vk.com/club1",
        post_external_id=post_id,
        url=f"https://vk.com/wall-1_{post_id}",
        text=text,
        published_at=published,
    )


def test_normalize_url() -> None:
    assert normalize_url(" vk.com/krsk_news/ ") == "https://vk.com/krsk_news"
    assert normalize_url("https://www.ok.ru/group/123?x=1#y") == "https://ok.ru/group/123"
    with pytest.raises(UnsupportedUrlError):
        normalize_url("   ")


def test_finalize_drops_empty_outside_and_duplicates() -> None:
    result = CollectResult(
        posts=[
            post("1"),
            post("1"),  # дубль того же размещения
            post("2", text="   "),  # пустой текст
            post("3", published=PERIOD.start - timedelta(seconds=1)),  # вне периода
            post("4", published=None),  # даты нет — остаётся
        ]
    )
    finalized, stats = finalize_result(result, PERIOD, limit=10)
    assert [p.post_external_id for p in finalized.posts] == ["1", "4"]
    assert (stats.received, stats.kept, stats.empty_text, stats.outside_period) == (5, 2, 1, 1)
    assert not finalized.truncated
    assert finalized.warnings == ["Пропущено постов без текста: 1"]


def test_finalize_period_bounds_are_inclusive() -> None:
    result = CollectResult(
        posts=[post("1", published=PERIOD.start), post("2", published=PERIOD.end)]
    )
    finalized, _ = finalize_result(result, PERIOD, limit=10)
    assert len(finalized.posts) == 2


def test_finalize_truncates_to_limit() -> None:
    result = CollectResult(posts=[post(str(i)) for i in range(5)])
    finalized, stats = finalize_result(result, PERIOD, limit=3)
    assert len(finalized.posts) == 3 and finalized.truncated and stats.kept == 3


def test_finalize_keeps_truncated_flag_from_connector() -> None:
    finalized, _ = finalize_result(CollectResult(posts=[post("1")], truncated=True), PERIOD, 10)
    assert finalized.truncated
