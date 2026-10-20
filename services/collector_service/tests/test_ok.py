"""Одноклассники на РЕАЛЬНЫХ страницах ok.ru (fixtures/ok/, сняты 2026-10-19 с группы НГС).

Момент загрузки страниц — 2026-10-19 13:53 UTC: от него считаются «сегодня» и «вчера».
"""

from datetime import UTC, datetime

import pytest

from collector_service.domain.enums import Health, Platform
from collector_service.domain.exceptions import (
    PlatformUnavailableError,
    SourceNotFoundError,
    UnsupportedUrlError,
)
from collector_service.domain.value_objects import Period
from collector_service.infra.connectors.ok import OkConnector
from collector_service.infra.ok.dates import parse_ok_date
from collector_service.infra.ok.pages import parse_topic_page, parse_topics_page
from tests.streams import gather
from tests.web_support import ScriptedWeb, read

NOW = datetime(2026, 10, 19, 13, 53, tzinfo=UTC)
GID = "54787706781713"
TOPICS = f"https://ok.ru/group/{GID}/topics"
LOADER = (
    "https://ok.ru/dk?cmd=AltGroupForumNewRB&st.gid=54787706781713&st.cmd=anonymGroupForum"
    "&st.gid=54787706781713&st.actualtopics=off&st.page={page}&st.lastelem=0%2C0%2C-112%2C125"
    "%2C-85%2C8%2C69%2C17"
)
GROUP_PAGE = read("ok/group.html")
FIRST = read("ok/group_topics.html")
SECOND = read("ok/group_topics_page2.html")


def connector(pages: dict[str, str | int]) -> tuple[OkConnector, ScriptedWeb]:
    web = ScriptedWeb(pages)
    return OkConnector(web, now=lambda: NOW), web


def period(start: datetime) -> Period:
    return Period(start=start, end=NOW)


# ---------- даты ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("добавлена сегодня в 16:30", datetime(2026, 10, 19, 13, 30, tzinfo=UTC)),
        ("добавлена вчера в 18:46", datetime(2026, 10, 18, 15, 46, tzinfo=UTC)),
        ("добавлена 17 октября в 23:15", datetime(2026, 10, 17, 20, 15, tzinfo=UTC)),
        ("17 окт 2025 в 09:00", datetime(2025, 10, 17, 6, 0, tzinfo=UTC)),
        ("31 декабря в 10:00", datetime(2025, 12, 31, 7, 0, tzinfo=UTC)),  # без года — прошлый
        ("16:30", datetime(2026, 10, 19, 13, 30, tzinfo=UTC)),  # только время = сегодня
        ("17 октября", None),  # нет времени — не выдумываем
        ("недавно", None),
    ],
)
def test_ok_dates_are_moscow_time(text: str, expected: datetime | None) -> None:
    assert parse_ok_date(text, NOW) == expected


# ---------- разбор страниц ----------


def test_topics_page_is_understood() -> None:
    page = parse_topics_page(FIRST, NOW)
    assert len(page.topics) == 20 and {t.gid for t in page.topics} == {GID}
    first = page.topics[0]
    assert first.tid == "158870686352657"
    assert first.url == f"https://ok.ru/group/{GID}/topic/158870686352657"
    assert first.group_name == "Новости Красноярска - НГС.НОВОСТИ"
    assert first.text.startswith("В Красноярске на четыре дня перекроют парковки")
    assert "<" not in first.text
    assert first.published_at == datetime(2026, 10, 19, 13, 30, tzinfo=UTC)
    assert (first.likes, first.reshares, first.comments) == (0, 0, 0)
    assert all(t.text and t.published_at for t in page.topics)
    assert page.cursor is not None and page.cursor.last_element == "0,0,-112,125,-85,8,69,17"


def test_topic_page_is_understood() -> None:
    topic = parse_topic_page(read("ok/topic.html"), NOW)
    assert topic is not None and (topic.gid, topic.tid) == (GID, "158870686352657")
    assert topic.text.startswith("В Красноярске на четыре дня")
    assert topic.published_at == datetime(2026, 10, 19, 13, 30, tzinfo=UTC)
    assert topic.group_name == "Новости Красноярска - НГС.НОВОСТИ"


# ---------- resolve ----------


async def test_resolve_by_short_name_and_by_group_id() -> None:
    ok, web = connector(
        {"https://ok.ru/ngs24": GROUP_PAGE, f"https://ok.ru/group/{GID}": GROUP_PAGE}
    )
    source = await ok.resolve("https://ok.ru/ngs24")
    assert (source.external_id, source.screen_name) == (GID, "ngs24")
    assert source.url == f"https://ok.ru/group/{GID}" and source.platform is Platform.OK
    assert source.name == "Новости Красноярска - НГС.НОВОСТИ"
    by_id = await ok.resolve(f"https://ok.ru/group/{GID}/topics")
    assert by_id.external_id == GID and by_id.screen_name == f"group/{GID}"


async def test_resolve_rejects_profiles_and_unknown_groups() -> None:
    ok, _ = connector({})
    with pytest.raises(UnsupportedUrlError):
        await ok.resolve("https://ok.ru/profile/123")
    with pytest.raises(UnsupportedUrlError):
        await ok.resolve("https://ok.ru")
    with pytest.raises(SourceNotFoundError):
        await ok.resolve("https://ok.ru/no_such_group")  # 404


# ---------- collect ----------


async def test_collect_one_day_needs_only_the_first_page() -> None:
    ok, web = connector({TOPICS: FIRST})
    start = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)
    result = await gather(ok.collect(GID, period(start), []), period(start), 300)
    assert result.posts and all(p.published_at and p.published_at >= start for p in result.posts)
    assert web.requested == [TOPICS]  # дошли до старых постов на первой странице — стоп
    assert not result.truncated
    post = result.posts[0]
    assert post.url == f"https://ok.ru/group/{GID}/topic/{post.post_external_id}"
    assert post.source_url == f"https://ok.ru/group/{GID}" and post.title is None


async def test_collect_pages_through_the_feed_loader() -> None:
    ok, web = connector({TOPICS: FIRST, LOADER.format(page=2): SECOND})
    start = datetime(2026, 10, 18, 0, 0, tzinfo=UTC)
    result = await gather(ok.collect(GID, period(start), []), period(start), 300)
    assert web.requested == [TOPICS, LOADER.format(page=2)]
    [(_, form, headers)] = web.posted  # подгрузка — как у самой страницы
    assert form == {"fetch": "false"} and headers["Referer"] == TOPICS
    dates = [p.published_at for p in result.posts]
    assert min(d for d in dates if d) >= start and len(result.posts) > 20
    assert not result.truncated  # на второй странице дошли до 17 октября


async def test_collect_stops_honestly_when_the_feed_does_not_page_further() -> None:
    ok, web = connector({TOPICS: FIRST, LOADER.format(page=2): SECOND})  # третьей нет → 404
    start = datetime(2026, 10, 1, tzinfo=UTC)
    with_404 = await gather(ok.collect(GID, period(start), []), period(start), 300)
    assert len(with_404.posts) == 40 and with_404.truncated
    assert "Сбор прерван" in with_404.warnings[0]


async def test_collect_rejects_bad_id_and_reports_unavailable() -> None:
    ok, _ = connector({TOPICS: 503})
    with pytest.raises(UnsupportedUrlError):
        await gather(ok.collect("ngs24", period(NOW), []), period(NOW), 10)
    with pytest.raises(PlatformUnavailableError):
        await gather(ok.collect(GID, period(NOW), []), period(NOW), 10)


# ---------- PostReader и health ----------


async def test_read_post_for_search_results() -> None:
    url = f"https://ok.ru/group/{GID}/topic/158870686352657"
    ok, _ = connector({url: read("ok/topic.html")})
    assert ok.accepts(url) and ok.accepts("https://ok.ru/ngs24/topic/1")
    assert not ok.accepts(f"https://ok.ru/group/{GID}") and not ok.accepts("https://ok.ru/ngs24")
    post = await ok.read_post(url)
    assert post is not None and post.url == url and post.platform is Platform.OK


async def test_health() -> None:
    ok, _ = connector({"https://ok.ru/ngs24": GROUP_PAGE})
    info = await ok.health()
    assert info.health is Health.OK and info.source_mode_supported
    assert not info.global_mode_supported  # «везде» добавляет только WithSiteSearch
    down, _ = connector({"https://ok.ru/ngs24": 403})
    info = await down.health()
    assert info.health is Health.UNAVAILABLE and "не робот" in info.note
