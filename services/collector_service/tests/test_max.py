"""MAX через Bot API на синтетических ответах (формат — по dev.max.ru, реальных ответов нет:
нужен токен бота). Сеть подменена httpx.MockTransport."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from collector_service.domain.enums import Health
from collector_service.domain.exceptions import (
    PlatformUnavailableError,
    SourcePrivateError,
    UnsupportedUrlError,
)
from collector_service.domain.value_objects import Period
from collector_service.infra.connectors.max import MaxConnector
from collector_service.infra.max_api.client import MaxApiClient
from collector_service.infra.vk_api.limiter import RateLimiter
from tests.streams import gather

PERIOD = Period(
    start=datetime(2026, 10, 10, tzinfo=UTC), end=datetime(2026, 10, 19, 23, 59, tzinfo=UTC)
)
CHAT = {
    "chat_id": -70001,
    "type": "channel",
    "title": "Новости Красноярска",
    "link": "https://max.ru/krsk_news_test",
    "participants_count": 5400,
    "is_public": True,
}


def ms(day: int, hour: int = 12) -> int:
    return int(datetime(2026, 10, day, hour, tzinfo=UTC).timestamp() * 1000)


def message(mid: str, day: int, text: str = "Текст поста", url: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "timestamp": ms(day),
        "body": {"mid": mid, "text": text},
        "stat": {"views": 120},
        "recipient": {"chat_id": -70001, "chat_type": "channel"},
    }
    if url:
        out["url"] = f"https://max.ru/krsk_news_test/{mid}"
    return out


Handler = Callable[[httpx.Request], httpx.Response]


def connector(handler: Handler, token: str = "tkn") -> MaxConnector:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return MaxConnector(MaxApiClient(http, token=token, limiter=RateLimiter(0)))


async def test_resolve_channel_by_public_link() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=CHAT)

    source = await connector(handler).resolve("https://max.ru/krsk_news_test")
    assert (source.external_id, source.name, source.members_count) == (
        "-70001",
        "Новости Красноярска",
        5400,
    )
    assert seen[0].url.path == "/chats/krsk_news_test"
    assert seen[0].headers["Authorization"] == "tkn"  # без Bearer, не в URL
    assert "tkn" not in str(seen[0].url)
    with pytest.raises(UnsupportedUrlError):
        await connector(handler).resolve("https://max.ru/a/b")


async def test_collect_pages_back_until_period_start() -> None:
    pages = [
        {"messages": [message(f"m{100 - i}", 19 - (i % 5)) for i in range(100)]},
        {"messages": [message("2", 11), message("1", 9), message("0", 8, url=False)]},
    ]
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/chats/"):
            return httpx.Response(200, json=CHAT)
        calls.append(request)
        return httpx.Response(200, json=pages[len(calls) - 1])

    max_ = connector(handler)
    result = await gather(max_.collect("-70001", PERIOD, []), PERIOD, 1000)
    assert len(calls) == 2
    assert calls[0].url.params["count"] == "100" and calls[0].url.params["chat_id"] == "-70001"
    assert int(calls[1].url.params["from"]) == ms(15) - 1  # дальше — старше самого старого
    ids = [p.post_external_id for p in result.posts]
    assert "1" not in ids and "2" in ids  # 9 октября — вне периода
    post = result.posts[0]
    assert post.url == "https://max.ru/krsk_news_test/m100" and post.metrics.views == 120
    assert post.source_name == "Новости Красноярска"
    assert any("без ссылки на пост" in w for w in result.warnings)


async def test_errors_and_health() -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"code": "chat.denied"})

    with pytest.raises(SourcePrivateError):
        await connector(forbidden).resolve("https://max.ru/x")
    no_token = connector(forbidden, token="")
    info = await no_token.health()
    assert info.health is Health.UNAVAILABLE and "MAX_BOT_TOKEN" in info.note
    with pytest.raises(PlatformUnavailableError):
        await gather(no_token.search(["ДТП"], PERIOD, []), PERIOD, 10)

    ok = connector(lambda r: httpx.Response(200, json={"user_id": 1, "is_bot": True}))
    info = await ok.health()
    assert info.health is Health.OK and info.source_mode_supported
    assert not info.global_mode_supported
