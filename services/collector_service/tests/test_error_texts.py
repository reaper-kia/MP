"""B1-13: сотрудник видит человеческий текст, подробность — только в лог.

search_service показывает str(ошибки сборщика) в интерфейсе как есть, поэтому в нём не должно
быть «rpc error», кодов HTTP, названий методов API и переменных окружения. Всё это — в detail.
"""

import base64
import logging
import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import grpc
import httpx
import pytest

from collector_service.domain import messages
from collector_service.domain.exceptions import (
    CollectorError,
    PlatformUnavailableError,
    log_text,
)
from collector_service.domain.value_objects import Page, Period
from collector_service.infra.connectors.max import MaxConnector
from collector_service.infra.connectors.ok import OkConnector
from collector_service.infra.connectors.site_search import SiteSearch, WithSearchFallback
from collector_service.infra.connectors.vk import VkConnector
from collector_service.infra.max_api.client import MaxApiClient
from collector_service.infra.vk_api.client import VkApiClient
from collector_service.infra.vk_api.limiter import RateLimiter
from collector_service.infra.vk_api.mapping import owner_id_from_external
from collector_service.infra.web.fetcher import HostLimiters, HttpxWebFetcher
from collector_service.infra.yandex_search.client import SearchHit, YandexSearchClient
from collector_service.transport.grpc.errors import grpc_errors
from tests.vk_support import ScriptedVk, network_down, ok, vk_error
from tests.web_support import ScriptedWeb

PERIOD = Period(
    start=datetime(2026, 10, 5, tzinfo=UTC), end=datetime(2026, 10, 19, 23, 59, tzinfo=UTC)
)
RPC_DENIED = (
    "rpc error: code = PermissionDenied desc = Permission to "
    "[resource-manager.folder b1g..., search-api.webSearch.use] denied"
)

# чего не должно быть в тексте для сотрудника
TECHNICAL = re.compile(
    r"rpc error|PermissionDenied|HTTP|\b[1-5]\d\d\b|\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b"
    r"|newsfeed\.|wall\.|users\.|Error\b|\.py\b"
)


def assert_human(exc: BaseException) -> None:
    text = str(exc)
    assert text, "пустой текст ошибки"
    assert not TECHNICAL.search(text), f"технические детали в тексте для сотрудника: {text!r}"


async def no_sleep(seconds: float) -> None:
    return None


async def gather(pages: AsyncIterator[Page]) -> list[Page]:
    return [page async for page in pages]


# ───────────────────────── Яндекс: 401/403, не настроен, не ответил ─────────────────────────


class Poster:
    def __init__(self, status: int, payload: Any) -> None:
        self.status, self.payload = status, payload

    async def post_json(
        self, url: str, body: Mapping[str, Any], headers: Mapping[str, str]
    ) -> tuple[int, Any]:
        return self.status, self.payload


def yandex(status: int, payload: Any = None, key: str = "key") -> YandexSearchClient:
    return YandexSearchClient(
        Poster(status, payload), folder_id="b1g", api_key=key, limiter=RateLimiter(0)
    )


@pytest.mark.parametrize("status", [401, 403])
async def test_yandex_denied_is_human_and_reason_goes_to_log(status: int) -> None:
    with pytest.raises(PlatformUnavailableError) as info:
        await yandex(status, {"code": 7, "message": RPC_DENIED}).search("ДТП site:ok.ru")
    assert str(info.value) == messages.GLOBAL_SEARCH_DENIED
    assert "Поиск по вашим источникам работает" in str(info.value)
    assert_human(info.value)
    assert "rpc error" in info.value.detail and str(status) in info.value.detail
    assert "YC_SEARCH_API_KEY" in log_text(info.value)


@pytest.mark.parametrize(
    ("status", "payload", "key", "expected"),
    [
        (200, {}, "", messages.GLOBAL_SEARCH_NOT_CONFIGURED),
        (500, {}, "key", messages.GLOBAL_SEARCH_DOWN),
        (503, None, "key", messages.GLOBAL_SEARCH_DOWN),
        (429, {}, "key", messages.GLOBAL_SEARCH_QUOTA),
        (
            200,
            {"rawData": base64.b64encode(b"<not xml").decode()},
            "key",
            messages.GLOBAL_SEARCH_DOWN,
        ),
    ],
)
async def test_yandex_other_failures_are_human(
    status: int, payload: Any, key: str, expected: str
) -> None:
    with pytest.raises(CollectorError) as info:
        await yandex(status, payload, key=key).search("x")
    assert str(info.value) == expected
    assert_human(info.value)
    assert info.value.detail


# ───────────────────────── VK 1051 — заметка, а не ошибка цели ─────────────────────────


class Yandex:
    def __init__(self, urls: Sequence[str], configured: bool = True) -> None:
        self.urls, self.configured = list(urls), configured

    async def search(self, text: str, page: int = 0) -> list[SearchHit]:
        return [SearchHit(url=u, title="", snippet="") for u in self.urls] if page == 0 else []


def vk_client(vk: ScriptedVk, token: str = "t") -> VkApiClient:
    return VkApiClient(vk, token=token, version="5.199", limiter=RateLimiter(0), sleep=no_sleep)


def vk_fallback(vk: ScriptedVk, search: Any) -> WithSearchFallback:
    connector = VkConnector(vk_client(vk))
    return WithSearchFallback(connector, SiteSearch(search, "vk.com", connector))


ITEM = {
    "id": 5,
    "owner_id": -10,
    "date": int(datetime(2026, 10, 10, 9, tzinfo=UTC).timestamp()),
    "text": "ДТП на Мира",
}


async def test_vk_1051_is_a_note_not_a_target_error() -> None:
    vk = ScriptedVk(
        newsfeed_search=vk_error(1051),
        wall_getById=ok({"items": [ITEM], "groups": [{"id": 10, "name": "Новости"}]}),
    )
    pages = await gather(
        vk_fallback(vk, Yandex(["https://vk.com/wall-10_5"])).search(["ДТП"], PERIOD, [])
    )
    warnings = [w for page in pages for w in page.warnings]
    assert sum(len(page.posts) for page in pages) == 1
    assert any(messages.VIA_YANDEX_NOTE in w for w in warnings)
    assert not any("1051" in w or "newsfeed" in w for w in warnings)


async def test_vk_1051_without_yandex_key_is_human() -> None:
    vk = ScriptedVk(newsfeed_search=vk_error(1051))
    with pytest.raises(PlatformUnavailableError) as info:
        await gather(vk_fallback(vk, Yandex([], configured=False)).search(["ДТП"], PERIOD, []))
    assert str(info.value) == messages.GLOBAL_SEARCH_NOT_CONFIGURED
    assert_human(info.value)


# ───────────────────────── таймаут / 5xx площадки ─────────────────────────


async def test_vk_network_down_is_no_answer() -> None:
    with pytest.raises(PlatformUnavailableError) as info:
        await vk_client(ScriptedVk(wall_get=network_down())).call("wall.get", owner_id=-1)
    assert str(info.value) == messages.no_answer("ВКонтакте")
    assert_human(info.value)


@pytest.mark.parametrize("code", [5, 6, 10, 15, 100, 77])
async def test_vk_api_error_codes_are_human(code: int) -> None:
    with pytest.raises(CollectorError) as info:
        await vk_client(ScriptedVk(wall_get=vk_error(code))).call("wall.get", owner_id=-1)
    assert_human(info.value)
    assert f"ошибка {code}" in info.value.detail


def max_connector(status: int, token: str = "tkn") -> MaxConnector:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status)))
    return MaxConnector(MaxApiClient(http, token=token, limiter=RateLimiter(0)))


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_max_5xx_is_no_answer(status: int) -> None:
    with pytest.raises(PlatformUnavailableError) as info:
        await max_connector(status).resolve("https://max.ru/krsk_news_test")
    assert str(info.value) == messages.no_answer("MAX")
    assert_human(info.value)
    assert str(status) in info.value.detail


@pytest.mark.parametrize("status", [401, 403, 404, 429, 418])
async def test_max_4xx_are_human(status: int) -> None:
    with pytest.raises(CollectorError) as info:
        await max_connector(status).resolve("https://max.ru/krsk_news_test")
    assert_human(info.value)


async def test_max_without_token_is_human() -> None:
    with pytest.raises(PlatformUnavailableError) as info:
        await max_connector(200, token="").resolve("https://max.ru/krsk_news_test")
    assert str(info.value) == messages.not_configured("MAX")
    assert "MAX_BOT_TOKEN" in info.value.detail


def web_fetcher(handler: Callable[[httpx.Request], httpx.Response]) -> HttpxWebFetcher:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpxWebFetcher(http, HostLimiters(0), sleep=no_sleep)


@pytest.mark.parametrize("status", [500, 502, 504])
async def test_page_5xx_is_no_answer(status: int) -> None:
    fetcher = web_fetcher(lambda _: httpx.Response(status))
    with pytest.raises(PlatformUnavailableError) as info:
        await fetcher.get("https://ok.ru/group/1/topics", what="Одноклассники")
    assert str(info.value) == messages.no_answer("Одноклассники")
    assert_human(info.value)


async def test_page_timeout_is_no_answer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(PlatformUnavailableError) as info:
        await web_fetcher(handler).get("https://ok.ru/group/1/topics", what="Одноклассники")
    assert str(info.value) == messages.no_answer("Одноклассники")
    assert "ReadTimeout" in info.value.detail


@pytest.mark.parametrize("status", [403, 404, 429, 418])
async def test_page_4xx_are_human(status: int) -> None:
    fetcher = web_fetcher(lambda _: httpx.Response(status))
    with pytest.raises(CollectorError) as info:
        await fetcher.get("https://ok.ru/group/1/topics", what="Одноклассники")
    assert_human(info.value)


# ───────────────────────── «Некорректный id источника» (verify_…) ─────────────────────────


@pytest.mark.parametrize("external_id", ["verify_krsk_news", "0", ""])
def test_vk_bad_source_id_says_check_link(external_id: str) -> None:
    with pytest.raises(CollectorError) as info:
        owner_id_from_external(external_id)
    assert str(info.value) == messages.source_not_found("ВКонтакте")
    assert messages.SOURCE_NOT_FOUND[1:] in str(info.value)


@pytest.mark.parametrize(
    ("connector", "platform"),
    [
        (lambda: OkConnector(ScriptedWeb({})), "Одноклассники"),
        (lambda: max_connector(200), "MAX"),
    ],
)
async def test_ok_and_max_bad_source_id_says_check_link(
    connector: Callable[[], Any], platform: str
) -> None:
    with pytest.raises(CollectorError) as info:
        await gather(connector().collect("verify_smoke", PERIOD, []))
    assert str(info.value) == messages.source_not_found(platform)
    assert "verify_smoke" in info.value.detail


# ───────────────────────── gRPC: наружу — текст, в лог — подробность ─────────────────────────


class Context:
    def __init__(self) -> None:
        self.aborted: tuple[grpc.StatusCode, str] | None = None

    async def abort(self, code: grpc.StatusCode, details: str, trailing_metadata: Any = ()) -> None:
        self.aborted = (code, details)


async def test_grpc_details_carry_only_the_human_text() -> None:
    error = PlatformUnavailableError(
        messages.GLOBAL_SEARCH_DENIED, detail=f"Яндекс Поиск: ключ не принят (403: {RPC_DENIED})"
    )

    class Servicer:
        @grpc_errors
        async def Search(self, request: object, context: Any) -> object:  # noqa: N802
            raise error

    context = Context()
    with pytest.raises(PlatformUnavailableError):
        await Servicer().Search(object(), context)
    assert context.aborted == (grpc.StatusCode.UNAVAILABLE, messages.GLOBAL_SEARCH_DENIED)


async def test_failed_query_logs_the_detail(caplog: pytest.LogCaptureFixture) -> None:
    from collector_service.applications.behaviors import LoggingBehavior

    error = PlatformUnavailableError(messages.no_answer("MAX"), detail="MAX: HTTP 502")

    async def call_next() -> object:
        raise error

    with caplog.at_level(logging.WARNING), pytest.raises(PlatformUnavailableError):
        await LoggingBehavior()(object(), call_next)  # type: ignore[arg-type]
    assert "HTTP 502" in caplog.text and messages.no_answer("MAX") in caplog.text


def test_errors_without_detail_still_work() -> None:
    plain = CollectorError("просто текст")
    assert plain.detail == "" and log_text(plain) == "просто текст"
