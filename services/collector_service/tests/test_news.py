"""Новостные сайты через RSS на синтетической ленте (fixtures/news/synthetic_feed.xml)."""

from datetime import UTC, datetime

import pytest

from collector_service.domain.enums import Health, Platform
from collector_service.domain.exceptions import UnsupportedUrlError
from collector_service.domain.value_objects import Period
from collector_service.infra.connectors.news import NewsConnector, canonical_url
from collector_service.infra.news.rss import parse_feed
from collector_service.infra.news.sites import parse_sites
from tests.streams import gather
from tests.web_support import ScriptedWeb, read

FEED_URL = "https://news-test.ru/rss/"
SITES = parse_sites(f"news-test.ru|{FEED_URL}|Новости-тест; bad-site.ru|https://bad-site.ru/rss")
PERIOD = Period(
    start=datetime(2026, 10, 5, tzinfo=UTC), end=datetime(2026, 10, 19, 23, 59, tzinfo=UTC)
)
ARTICLE = (
    "<html><body><article><p>"
    + "Учения МЧС прошли в торговом центре Канска. " * 10
    + "</p><p>Эвакуировали 300 человек.</p></article></body></html>"
)


def web(**extra: str | int) -> ScriptedWeb:
    return ScriptedWeb(
        {
            FEED_URL: read("news/synthetic_feed.xml"),
            "https://news-test.ru/text/society/2026/10/10/102/": ARTICLE,
            **extra,
        }
    )


def test_parse_sites_and_feed() -> None:
    assert [s.host for s in SITES] == ["news-test.ru", "bad-site.ru"]
    assert SITES[1].name == "bad-site.ru"
    feed = parse_feed(read("news/synthetic_feed.xml"))
    first = feed.items[0]
    assert feed.title == "Тестовые новости Красноярска"
    assert (
        first.full_text
        and first.text == "На трассе Р-255 столкнулись два грузовика.\nПострадавших нет."
    )
    assert first.published_at == datetime(2026, 10, 18, 7, 5, tzinfo=UTC)  # +07:00 → UTC
    assert feed.items[3].published_at is None


def test_canonical_url_drops_utm_and_fragment() -> None:
    assert (
        canonical_url("http://News-Test.ru/a/?utm_source=rss&id=7#x")
        == "https://news-test.ru/a/?id=7"
    )


async def test_collect_takes_period_items_and_opens_short_articles() -> None:
    scripted = web()
    connector = NewsConnector(SITES, scripted)
    result = await gather(connector.collect("news-test.ru", PERIOD, []), PERIOD, 100)
    by_title = {p.title: p for p in result.posts}
    assert set(by_title) == {"ДТП на Р-255 под Красноярском", "Учения МЧС в Канске", "Без даты"}
    dtp = by_title["ДТП на Р-255 под Красноярском"]
    assert dtp.url == "https://news-test.ru/text/incidents/2026/10/18/101/?id=7"
    assert dtp.post_external_id == "/text/incidents/2026/10/18/101"
    assert dtp.platform is Platform.NEWS and dtp.source_name == "Новости-тест"
    assert by_title["Учения МЧС в Канске"].text.startswith("Учения МЧС прошли")  # со страницы
    assert by_title["Без даты"].text == "Текст без даты публикации"  # статья не открылась → анонс
    # полный текст из ленты — статью не открываем
    assert not any("incidents" in u for u in scripted.requested[1:])


async def test_search_filters_feed_items_by_phrase_words() -> None:
    connector = NewsConnector(SITES, web())
    result = await gather(connector.search(["ДТП Красноярск"], PERIOD, []), PERIOD, 100)
    assert [p.title for p in result.posts] == ["ДТП на Р-255 под Красноярском"]
    assert any("не по архиву" in w for w in result.warnings)
    assert any("bad-site.ru" in w for w in result.warnings)  # лента не открылась — сказали


async def test_resolve_and_unknown_site() -> None:
    connector = NewsConnector(SITES, web())
    source = await connector.resolve("https://news-test.ru/text/anything")
    assert (source.external_id, source.name) == ("news-test.ru", "Новости-тест")
    with pytest.raises(UnsupportedUrlError):
        await connector.resolve("https://other.ru/")


async def test_health() -> None:
    info = await NewsConnector(SITES, web()).health()
    assert info.health is Health.DEGRADED and "1 из 2" in info.note
    assert (await NewsConnector([], web()).health()).health is Health.UNAVAILABLE


@pytest.mark.parametrize(
    ("name", "full_text"), [("news/ngs24_rss.xml", False), ("news/krsk_aif_rss.xml", True)]
)
def test_real_feeds_are_understood(name: str, full_text: bool) -> None:
    """Настоящие ленты (сняты 2026-10-19): ссылка, дата с поясом, текст без HTML."""
    feed = parse_feed(read(name).encode())
    assert len(feed.items) == 5
    for item in feed.items:
        assert item.link.startswith("http") and item.title and item.text
        assert item.published_at is not None and item.published_at.tzinfo is not None
        assert "<" not in item.text and item.full_text is full_text


def test_default_sites_are_valid() -> None:
    from collector_service.infra.config import DEFAULT_NEWS_SITES

    sites = parse_sites(DEFAULT_NEWS_SITES)
    assert {s.host for s in sites} >= {"ngs24.ru", "newslab.ru", "krsk.aif.ru"}
    assert all(s.feed_url.startswith("https://") for s in sites)
