"""Ядро applications: поведения Mediator, бюджет времени, частичный ответ при сбое."""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from collector_service.applications.budget import Budget
from collector_service.applications.collecting import drain
from collector_service.applications.context import RequestContext
from collector_service.applications.limits import CollectLimits
from collector_service.applications.mediator import Mediator, Query
from collector_service.applications.queries.sources import (
    CollectFromSourceQuery,
    ResolveSourceQuery,
)
from collector_service.dependencies import build_mediator
from collector_service.domain.enums import Platform
from collector_service.domain.exceptions import PlatformUnavailableError
from collector_service.domain.services import PostAccumulator
from collector_service.domain.value_objects import Page, Period, RawPost
from collector_service.infra.cache import TtlCache
from collector_service.infra.connectors.fake import FakeConnector
from collector_service.infra.connectors.registry import InMemoryConnectorRegistry

CTX = RequestContext(request_id="t")
PERIOD = Period(
    start=datetime(2026, 10, 1, tzinfo=UTC), end=datetime(2026, 10, 19, 23, 59, tzinfo=UTC)
)


def post(i: int) -> RawPost:
    return RawPost(
        platform=Platform.VK,
        source_external_id="-1",
        source_name="s",
        source_url="https://vk.com/club1",
        post_external_id=str(i),
        url=f"https://vk.com/wall-1_{i}",
        text=f"пост {i}",
        published_at=PERIOD.start,
    )


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


# ---------- Mediator и поведения ----------


@dataclass(frozen=True)
class Ping(Query[str]):
    value: str


class Echo:
    async def handle(self, query: Ping) -> str:
        return query.value


async def test_behaviors_wrap_handler_in_registration_order() -> None:
    calls: list[str] = []

    def behavior(name: str):  # type: ignore[no-untyped-def]
        async def run(query, call_next):  # type: ignore[no-untyped-def]
            calls.append(f"{name}>")
            result = await call_next()
            calls.append(f"<{name}")
            return result

        return run

    mediator = Mediator(behaviors=[behavior("outer"), behavior("inner")])
    mediator.register(Ping, Echo())
    assert await mediator.send(Ping("x")) == "x"
    assert calls == ["outer>", "inner>", "<inner", "<outer"]


async def test_resolve_is_cached_for_ttl_and_errors_are_not() -> None:
    class CountingFake(FakeConnector):
        calls = 0

        async def resolve(self, url: str):  # type: ignore[no-untyped-def]
            CountingFake.calls += 1
            return await super().resolve(url)

    clock = Clock()
    registry = InMemoryConnectorRegistry([CountingFake(Platform.VK, delay_seconds=0)])
    mediator = build_mediator(
        registry, CollectLimits(300, 500), TtlCache(clock=clock), resolve_cache_ttl=600
    )
    first = await mediator.send(ResolveSourceQuery(ctx=CTX, url="vk.com/krsk_news"))
    again = await mediator.send(ResolveSourceQuery(ctx=CTX, url="https://VK.com/krsk_news/"))
    assert first == again and CountingFake.calls == 1  # та же ссылка в другой записи — из кэша
    clock.now += 601
    await mediator.send(ResolveSourceQuery(ctx=CTX, url="vk.com/krsk_news"))
    assert CountingFake.calls == 2

    for _ in range(2):  # закрытая группа — ошибка, не кэшируется
        with pytest.raises(Exception, match="закрыта"):
            await mediator.send(ResolveSourceQuery(ctx=CTX, url="vk.com/closed"))


async def test_logging_behavior_writes_one_line_without_texts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = InMemoryConnectorRegistry([FakeConnector(Platform.VK, delay_seconds=0)])
    mediator = build_mediator(registry, CollectLimits(300, 500))
    with caplog.at_level(logging.INFO, logger="collector_service.queries"):
        await mediator.send(
            CollectFromSourceQuery(
                ctx=RequestContext("req-42"),
                platform=Platform.VK,
                source_external_id="g",
                period=PERIOD,
            )
        )
    [line] = [r.getMessage() for r in caplog.records if r.name == "collector_service.queries"]
    assert "CollectFromSourceQuery request_id=req-42 done in" in line
    assert "[FAKE]" not in line


# ---------- бюджет и поток страниц ----------


def test_budget_takes_the_smaller_of_own_limit_and_caller_deadline() -> None:
    clock = Clock()
    assert Budget.start(50, None, clock).seconds == 50
    assert Budget.start(50, 30, clock).seconds == 27  # 30 − запас 3 с
    assert Budget.start(50, 1, clock).seconds == 0
    budget = Budget.start(10, None, clock)
    clock.now += 4
    assert budget.remaining() == 6 and not budget.expired()
    clock.now += 7
    assert budget.expired()


async def slow_pages() -> AsyncIterator[Page]:
    yield Page(posts=[post(1), post(2)])
    await asyncio.sleep(5)
    yield Page(posts=[post(3)])


async def test_drain_stops_on_budget_and_returns_what_it_has() -> None:
    acc = PostAccumulator(PERIOD, 100)
    await drain(slow_pages(), acc, Budget.start(0.05, None))
    result, _ = acc.result()
    assert [p.post_external_id for p in result.posts] == ["1", "2"]
    assert result.truncated and "остановлен по времени" in result.warnings[0]


async def failing_after_first_page() -> AsyncIterator[Page]:
    yield Page(posts=[post(1)])
    raise PlatformUnavailableError("ВКонтакте не отвечает")


async def failing_at_once() -> AsyncIterator[Page]:
    raise PlatformUnavailableError("ВКонтакте не отвечает")
    yield Page()


async def test_drain_failure_after_first_page_is_partial_result() -> None:
    acc = PostAccumulator(PERIOD, 100)
    await drain(failing_after_first_page(), acc, Budget.start(10, None))
    result, _ = acc.result()
    assert len(result.posts) == 1 and result.truncated
    assert "Сбор прерван: ВКонтакте не отвечает" in result.warnings[0]


async def test_drain_failure_on_first_page_is_an_error() -> None:
    with pytest.raises(PlatformUnavailableError):
        await drain(failing_at_once(), PostAccumulator(PERIOD, 100), Budget.start(10, None))


async def test_drain_does_not_ask_for_more_pages_after_limit() -> None:
    asked = 0

    async def pages() -> AsyncIterator[Page]:
        nonlocal asked
        for i in range(10):
            asked += 1
            yield Page(posts=[post(2 * i), post(2 * i + 1)])

    acc = PostAccumulator(PERIOD, 3)
    await drain(pages(), acc, Budget.start(10, None))
    result, _ = acc.result()
    assert len(result.posts) == 3 and result.truncated and asked == 2


async def test_collect_handler_honours_caller_deadline() -> None:
    class Slow(FakeConnector):
        async def collect(self, source_external_id, period, keywords):  # type: ignore[no-untyped-def,override]
            async for page in slow_pages():
                yield page

    registry = InMemoryConnectorRegistry([Slow(Platform.VK, delay_seconds=0)])
    mediator = build_mediator(registry, CollectLimits(300, 500, budget_seconds=50))
    result = await mediator.send(
        CollectFromSourceQuery(
            ctx=RequestContext("t", time_remaining=3.1),  # gRPC deadline почти истёк
            platform=Platform.VK,
            source_external_id="g",
            period=PERIOD,
        )
    )
    assert len(result.posts) == 2 and result.truncated
