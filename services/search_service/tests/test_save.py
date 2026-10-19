from datetime import UTC, date, datetime

import pytest

from search_service.applications.handlers.save import SaveHandler, make_title
from search_service.applications.ports.collector_client import RawPost
from search_service.domain.entities import Search, SearchTarget
from search_service.domain.enums import DateStatus
from search_service.domain.value_objects import Period
from tests.fakes import InMemoryUoW


@pytest.fixture
def uow():
    return InMemoryUoW()


def make_search():
    return Search(
        query="q",
        period=Period(date(2026, 1, 1), date(2026, 1, 31)),
        mode="selected",
    )


def make_post(**overrides) -> RawPost:
    base = dict(
        platform="vk",
        source_external_id="src1",
        post_external_id="p1",
        url="https://vk.com/wall-1_1",
        source_name="Новости",
        source_url="https://vk.com/news",
        text="Текст поста про безопасность дорожного движения",
        title="Заголовок",
        published_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        metrics={"views": 100},
    )
    base.update(overrides)
    return RawPost(**base)


@pytest.mark.asyncio
async def test_same_post_found_twice_is_one_record(uow):
    search = make_search()
    target = SearchTarget(kind="source", platform="vk", name="n")
    search.targets = [target]
    handler = SaveHandler(uow)
    posts = [make_post(), make_post()]  # одинаковый post_external_id
    results1 = await handler.save_posts(search, target, posts)
    results2 = await handler.save_posts(search, target, [make_post()])
    assert len(results1) == 1
    assert len(results2) == 0  # дедуп сработал


@pytest.mark.asyncio
async def test_unknown_date_not_marked_in_period(uow):
    search = make_search()
    target = SearchTarget(kind="source", platform="vk", name="n")
    handler = SaveHandler(uow)
    results = await handler.save_posts(search, target, [make_post(published_at=None)])
    assert len(results) == 1
    assert results[0].date_status == DateStatus.UNKNOWN


@pytest.mark.asyncio
async def test_out_of_period_post_not_saved(uow):
    search = make_search()
    target = SearchTarget(kind="source", platform="vk", name="n")
    handler = SaveHandler(uow)
    results = await handler.save_posts(
        search,
        target,
        [make_post(published_at=datetime(2025, 1, 1, tzinfo=UTC))],
    )
    assert len(results) == 0


def test_make_title_with_title():
    post = make_post(title="Мой заголовок")
    title, source = make_title(post)
    assert title == "Мой заголовок"
    assert source == "title"


def test_make_title_from_long_text():
    long_text = "Очень длинный текст " * 20
    post = make_post(title=None, text=long_text)
    title, source = make_title(post)
    assert source == "post_start"
    assert title.endswith("…")
    assert len(title) <= 125
