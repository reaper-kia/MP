from datetime import date

import pytest

from search_service.domain.entities import Search, SearchTarget
from search_service.domain.enums import SearchStatus, TargetStatus
from search_service.domain.errors import DomainError, SearchInvalidParams
from search_service.domain.value_objects import Period


def test_period_from_after_to_raises():
    with pytest.raises(SearchInvalidParams):
        Period(from_date=date(2026, 1, 10), to_date=date(2026, 1, 5))


def test_period_too_long():
    with pytest.raises(SearchInvalidParams):
        Period(from_date=date(2020, 1, 1), to_date=date(2022, 1, 1), max_days=366)


def test_search_finish_with_unfinished_targets_raises():
    s = Search(query="q", period=Period(date(2026, 1, 1), date(2026, 1, 2)), mode="selected")
    s.targets = [SearchTarget(kind="source", platform="vk", name="n")]
    with pytest.raises(DomainError):
        s.finish()


def test_search_finish_all_failed():
    s = Search(query="q", period=Period(date(2026, 1, 1), date(2026, 1, 2)), mode="selected")
    t1 = SearchTarget(kind="source", platform="vk", name="n1")
    t2 = SearchTarget(kind="source", platform="ok", name="n2")
    t1.mark_failed("TIMEOUT", "timeout")
    t2.mark_failed("TIMEOUT", "timeout")
    s.targets = [t1, t2]
    s.finish()
    assert s.status == SearchStatus.FAILED


def test_search_finish_partial():
    s = Search(query="q", period=Period(date(2026, 1, 1), date(2026, 1, 2)), mode="selected")
    t1 = SearchTarget(kind="source", platform="vk", name="n1")
    t2 = SearchTarget(kind="source", platform="ok", name="n2")
    t1.mark_done(fetched=10)
    t2.mark_failed("TIMEOUT", "timeout")
    s.targets = [t1, t2]
    s.finish()
    assert s.status == SearchStatus.PARTIAL


def test_search_finish_completed():
    s = Search(query="q", period=Period(date(2026, 1, 1), date(2026, 1, 2)), mode="selected")
    t1 = SearchTarget(kind="source", platform="vk", name="n1")
    t1.mark_empty()
    s.targets = [t1]
    s.finish()
    assert s.status == SearchStatus.COMPLETED


def test_search_cancel_marks_unfinished_skipped():
    s = Search(query="q", period=Period(date(2026, 1, 1), date(2026, 1, 2)), mode="selected")
    t1 = SearchTarget(kind="source", platform="vk", name="n1")
    t1.start()
    s.targets = [t1]
    s.start()
    s.cancel()
    assert t1.status == TargetStatus.SKIPPED
    assert s.status == SearchStatus.CANCELLED
