"""Yandex Search API и режим «везде» через поисковик: только открывшиеся посты."""

import base64
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from collector_service.domain.enums import Health, Platform
from collector_service.domain.exceptions import PlatformUnavailableError, RateLimitedError
from collector_service.domain.value_objects import Page, Period, PlatformInfo, RawPost, SourceInfo
from collector_service.infra.connectors.site_search import SiteSearch, WithSiteSearch
from collector_service.infra.vk_api.limiter import RateLimiter
from collector_service.infra.yandex_search.client import YandexSearchClient, parse_xml
from tests.streams import gather
from tests.web_support import read

PERIOD = Period(
    start=datetime(2026, 10, 5, tzinfo=UTC), end=datetime(2026, 10, 19, 23, 59, tzinfo=UTC)
)
XML = read("yandex/synthetic_ok_search.xml").encode()


class Poster:
    def __init__(self, status: int = 200, payload: Any = None) -> None:
        self.status = status
        self.payload = (
            payload if payload is not None else {"rawData": base64.b64encode(XML).decode()}
        )
        self.calls: list[tuple[Mapping[str, Any], Mapping[str, str]]] = []

    async def post_json(
        self, url: str, body: Mapping[str, Any], headers: Mapping[str, str]
    ) -> tuple[int, Any]:
        self.calls.append((body, headers))
        return self.status, self.payload


def client(poster: Poster, key: str = "key") -> YandexSearchClient:
    return YandexSearchClient(
        poster, folder_id="b1g", api_key=key, region=62, limiter=RateLimiter(0)
    )


def test_parse_xml_keeps_hl_words_and_handles_nothing_found() -> None:
    hits = parse_xml(XML)
    assert [h.url for h in hits][0] == "https://ok.ru/group/70000001/topic/155000000001"
    assert hits[0].title == "Новости Красноярск" and hits[0].snippet == "На трассе ДТП"
    empty = b'<yandexsearch><response><error code="15">nothing</error></response></yandexsearch>'
    assert parse_xml(empty) == []


async def test_client_request_and_errors() -> None:
    poster = Poster()
    hits = await client(poster).search('"ДТП" site:ok.ru')
    body, headers = poster.calls[0]
    assert headers == {"Authorization": "Api-Key key"} and body["folderId"] == "b1g"
    assert body["query"]["queryText"] == '"ДТП" site:ok.ru' and body["region"] == "62"
    assert len(hits) == 3
    with pytest.raises(RateLimitedError):
        await client(Poster(status=429, payload={})).search("x")
    with pytest.raises(PlatformUnavailableError, match="отклонил доступ") as info:
        await client(Poster(status=403, payload={})).search("x")
    assert "ключ не принят" in info.value.detail
    denied = Poster(status=403, payload={"code": 7, "message": "Permission denied"})
    with pytest.raises(PlatformUnavailableError) as info:
        await client(denied).search("x")
    assert "Permission denied" in info.value.detail  # причина от Яндекса — в лог
    with pytest.raises(PlatformUnavailableError, match="не настроен"):
        await client(Poster(), key="").search("x")


class Reader:
    """PostReader: посты открываются, кроме одного, который «удалён»."""

    platform = Platform.OK

    def __init__(self) -> None:
        self.opened: list[str] = []

    def accepts(self, url: str) -> bool:
        return "/topic/" in url

    async def read_post(self, url: str) -> RawPost | None:
        self.opened.append(url)
        if url.endswith("0002"):
            return None
        return RawPost(
            platform=Platform.OK,
            source_external_id="70000001",
            source_name="Группа",
            source_url="https://ok.ru/group/70000001",
            post_external_id="155000000001",
            url=url,
            text="Текст поста",
            published_at=PERIOD.end,
        )


async def test_site_search_opens_only_post_links_and_drops_unopened() -> None:
    reader = Reader()
    search = SiteSearch(client(Poster()), "ok.ru", reader)
    result = await gather(search.search(["ДТП", "ДТП Красноярск"], PERIOD), PERIOD, 100)
    assert [p.post_external_id for p in result.posts] == ["155000000001"]
    assert len(reader.opened) == 2  # группа не открывалась; повтор между фразами — тоже
    assert any("покрытие неполное" in w for w in result.warnings)
    assert any("не открылись ссылки из поиска (1)" in w for w in result.warnings)


class Base:
    platform = Platform.OK
    title = "Одноклассники"
    hosts = ("ok.ru",)

    async def health(self) -> PlatformInfo:
        return PlatformInfo(Platform.OK, "Одноклассники", True, False, Health.OK, "")

    async def resolve(self, url: str) -> SourceInfo:
        raise NotImplementedError

    async def collect(
        self, source_external_id: str, period: Period, keywords: Sequence[str]
    ) -> AsyncIterator[Page]:
        yield Page()

    async def search(
        self, queries: Sequence[str], period: Period, region_terms: Sequence[str]
    ) -> AsyncIterator[Page]:
        yield Page()


async def test_with_site_search_health_depends_on_yandex_key() -> None:
    configured = WithSiteSearch(Base(), SiteSearch(client(Poster()), "ok.ru", Reader()))
    info = await configured.health()
    assert info.global_mode_supported and "покрытие неполное" in info.note
    missing = WithSiteSearch(Base(), SiteSearch(client(Poster(), key=""), "ok.ru", Reader()))
    info = await missing.health()
    assert info.source_mode_supported and not info.global_mode_supported
    assert "Yandex Search API" in info.note
