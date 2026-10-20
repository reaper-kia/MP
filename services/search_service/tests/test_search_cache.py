"""Кэш готовых подборок (B2-20): ключ, копия поиска, fresh, что не кэшируется, Redis недоступен."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import grpc
import pytest
import structlog
from common.v1 import common_pb2
from search.v1 import search_service_pb2 as pb
from search.v1 import search_service_pb2_grpc as pb_grpc

from search_service.applications.handlers.pipeline import Pipeline
from search_service.applications.ports.collector_client import RawPost, SourceInfo
from search_service.applications.search_cache import search_cache_key
from search_service.dependencies import build_mediator
from search_service.domain.enums import SearchMode, SearchStatus
from search_service.infra.runner import SearchRunner
from search_service.infra.search_cache import DisabledSearchCache, RedisSearchCache
from search_service.transport.grpc.server import create_server
from tests.fakes import FakeCollector, FakeMl, InMemoryUoW

CTX = common_pb2.RequestContext(request_id="test")
URL = "https://vk.com/krsk_news"
OTHER_URL = "https://vk.com/krsk_other"
TODAY = datetime.now(UTC)
FINAL = {
    pb.SEARCH_STATUS_COMPLETED,
    pb.SEARCH_STATUS_PARTIAL,
    pb.SEARCH_STATUS_FAILED,
    pb.SEARCH_STATUS_CANCELLED,
}


# ---------- ключ ----------


def key(query: str = "ДТП Красноярск", **kw: object) -> str:
    params: dict[str, object] = dict(
        query=query,
        period_from=date(2026, 10, 1),
        period_to=date(2026, 10, 20),
        mode=SearchMode.GLOBAL,
        platforms=["vk", "ok"],
        source_ids=[],
    )
    params.update(kw)
    return search_cache_key(**params)  # type: ignore[arg-type]


def test_key_normalizes_query_and_order() -> None:
    assert key("  ДТП   Красноярск ") == key("дтп красноярск")
    assert key(platforms=["ok", "vk", "vk"]) == key(platforms=["vk", "ok"])
    assert key().startswith("mp:search:v2:") and "дтп" not in key().lower()


def test_key_same_for_similar_wording() -> None:
    """Похожие формулировки — один ключ: порядок слов, предлоги, окончания, «ё», хэштеги."""
    base = key("ДТП в Красноярске")
    assert key("красноярск, ДТП") == base
    assert key("#ДТП #Красноярск") == base
    assert key("Безопасность дорожного движения в Красноярском крае") == key(
        "безопасность дорожное движение красноярский край"
    )
    assert key("#КрасноярскийКрай пожар") == key("пожар Красноярский край")
    assert key("Пожары в Ачинске") == key("ачинск пожар")
    assert key("Ёлка на площади") == key("елки площадь")


def test_key_differs_when_meaning_differs() -> None:
    assert key("ДТП в Красноярске") != key("ДТП в Ачинске")
    assert key("ДТП в Красноярске") != key("ДТП не в Красноярске")
    assert key("пожар") != key("пожар без жертв")
    assert key("ремонт моста") != key("ремонт дороги")


def test_key_differs_by_period_platform_source_and_mode() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    assert key() != key(period_to=date(2026, 10, 19))
    assert key() != key(period_from=date(2026, 9, 30))
    assert key() != key(platforms=["vk"])
    selected = key(mode=SearchMode.SELECTED, source_ids=[a, b])
    assert selected != key()
    assert selected == key(mode=SearchMode.SELECTED, source_ids=[b, a], platforms=["max"])
    assert selected != key(mode=SearchMode.SELECTED, source_ids=[a])


# ---------- фейк Redis ----------


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.ex: dict[str, int | None] = {}

    async def get(self, name: str) -> bytes | None:
        return self.data.get(name)

    async def set(self, name: str, value: str, *, ex: int | None = None) -> bool:
        self.data[name], self.ex[name] = value.encode(), ex
        return True

    async def delete(self, *names: str) -> int:
        return sum(self.data.pop(n, None) is not None for n in names)

    async def ping(self) -> bool:
        return True

    def ready(self) -> dict[str, bytes]:
        """Готовые подборки (без отметок «идёт»)."""
        return {k: v for k, v in self.data.items() if not k.startswith("mp:search:running:")}


class BrokenRedis:
    async def get(self, name: str) -> bytes | None:
        raise ConnectionError("redis down")

    async def set(self, name: str, value: str, *, ex: int | None = None) -> bool:
        raise ConnectionError("redis down")

    async def delete(self, *names: str) -> int:
        raise ConnectionError("redis down")

    async def ping(self) -> bool:
        raise ConnectionError("redis down")


class HangingRedis(BrokenRedis):
    async def get(self, name: str) -> bytes | None:
        await asyncio.sleep(5)
        return None


async def test_redis_search_cache_roundtrip_and_ttl() -> None:
    redis = FakeRedis()
    cache = RedisSearchCache(redis, ttl_seconds=1800)
    sid = uuid.uuid4()
    await cache.put("k", sid)
    assert redis.ex["k"] == 1800
    assert await cache.get("k") == sid
    assert await cache.get("missing") is None
    assert await cache.ping()


async def test_redis_slower_than_timeout_is_a_miss() -> None:
    cache = RedisSearchCache(HangingRedis(), ttl_seconds=60, timeout_seconds=0.05)
    started = asyncio.get_running_loop().time()
    assert await cache.get("k") is None
    assert asyncio.get_running_loop().time() - started < 1
    assert not await cache.ping()


# ---------- сквозь gRPC ----------


def post(n: int, text: str, source: str = "-2034") -> RawPost:
    return RawPost(
        platform="vk",
        source_external_id=source,
        post_external_id=str(n),
        url=f"https://vk.com/wall{source}_{n}",
        source_name="Красноярск: главное",
        source_url=URL,
        text=text,
        published_at=TODAY - timedelta(days=1),
        metrics={"views": 100 * n},
    )


@dataclass
class Stand:
    stub: pb_grpc.SearchServiceStub
    uow: InMemoryUoW
    collector: FakeCollector
    redis: object


async def make_stand(redis: object | None) -> tuple[Stand, SearchRunner, grpc.aio.Server]:
    uow, collector, ml = InMemoryUoW(), FakeCollector(), FakeMl()
    collector.sources[URL] = SourceInfo(
        platform="vk", external_id="-2034", screen_name="krsk_news", url=URL, name="Красноярск"
    )
    collector.sources[OTHER_URL] = SourceInfo(
        platform="vk", external_id="-77", screen_name="krsk_other", url=OTHER_URL, name="Другой"
    )
    collector.posts[("vk", "-2034")] = [
        post(1, "ГИБДД: аварийность на дорогах края снизилась"),
        post(2, "Ремонт моста через Енисей"),
    ]
    collector.posts[("vk", "-77")] = [post(1, "Другая новость", source="-77")]
    cache = (
        RedisSearchCache(redis, ttl_seconds=1800)  # type: ignore[arg-type]
        if redis is not None
        else DisabledSearchCache()
    )
    runner = SearchRunner(Pipeline(uow, collector, ml, asyncio.Semaphore(5), 10, cache=cache))
    server, port = await create_server(build_mediator(uow, collector, runner, cache), "127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    return Stand(pb_grpc.SearchServiceStub(channel), uow, collector, redis), runner, server


@pytest.fixture
async def stand() -> AsyncIterator[Stand]:
    s, runner, server = await make_stand(FakeRedis())
    try:
        yield s
    finally:
        await runner.cancel_all()
        await server.stop(grace=None)


async def wait_final(stub: pb_grpc.SearchServiceStub, search_id: str) -> pb.Search:
    for _ in range(200):
        r = await stub.GetSearch(pb.GetSearchRequest(context=CTX, search_id=search_id))
        if r.search.status in FINAL:
            return r.search
        await asyncio.sleep(0.02)
    raise AssertionError("поиск не завершился")


async def add_source(stub: pb_grpc.SearchServiceStub, url: str = URL) -> str:
    created = await stub.CreateSource(pb.CreateSourceRequest(context=CTX, url=url))
    return created.source.id


async def start(
    stub: pb_grpc.SearchServiceStub,
    source_ids: list[str],
    *,
    query: str = "безопасность дорожного движения",
    days: int = 30,
    fresh: bool = False,
) -> pb.Search:
    started = await stub.StartSearch(
        pb.StartSearchRequest(
            context=CTX,
            query=query,
            period_from=(TODAY - timedelta(days=days)).date().isoformat(),
            period_to=TODAY.date().isoformat(),
            mode=pb.SEARCH_MODE_SELECTED,
            source_ids=source_ids,
            fresh=fresh,
        )
    )
    return started.search


async def results_of(stub: pb_grpc.SearchServiceStub, search_id: str) -> pb.ListResultsResponse:
    return await stub.ListResults(
        pb.ListResultsRequest(
            context=CTX,
            search_id=search_id,
            limit=50,
            filter=pb.ResultFilter(include_excluded=True),
        )
    )


async def test_same_search_again_is_an_instant_copy(stand: Stand) -> None:
    stub = stand.stub
    source_id = await add_source(stub)
    first = await wait_final(stub, (await start(stub, [source_id])).id)
    assert first.status == pb.SEARCH_STATUS_COMPLETED and not first.HasField("cache")
    calls = len(stand.collector.calls)

    # тот же запрос другими пробелами и регистром — сразу финальный статус, сбор не идёт
    again = await start(stub, [source_id], query="  Безопасность   дорожного движения ")
    assert again.id != first.id
    assert again.status == pb.SEARCH_STATUS_COMPLETED
    assert again.HasField("cache") and again.cache.from_search_id == first.id
    assert again.cache.created_at.ToDatetime() == first.finished_at.ToDatetime()
    assert len(stand.collector.calls) == calls
    assert again.counts.total == first.counts.total == 2
    assert again.progress.percent == 100

    original = await results_of(stub, first.id)
    copy = await results_of(stub, again.id)
    assert sorted(r.publication_id for r in copy.results) == sorted(
        r.publication_id for r in original.results
    )
    assert {r.found_by_target_id for r in copy.results} == {again.targets[0].id}
    assert again.targets[0].id != first.targets[0].id
    groups = await stub.ListGroups(pb.ListGroupsRequest(context=CTX, search_id=again.id))
    assert groups.total == 2

    # исключение в копии не трогает исходный поиск
    excluded = await stub.SetExcluded(
        pb.SetExcludedRequest(
            context=CTX, search_id=again.id, result_ids=[copy.results[0].id], excluded=True
        )
    )
    assert excluded.counts.excluded == 1
    assert not any(r.excluded for r in (await results_of(stub, first.id)).results)

    # исключения исходного поиска не переезжают в следующую копию
    await stub.SetExcluded(
        pb.SetExcludedRequest(
            context=CTX, search_id=first.id, result_ids=[original.results[0].id], excluded=True
        )
    )
    third = await start(stub, [source_id])
    assert third.cache.from_search_id == first.id
    assert third.counts.excluded == 0 and third.counts.total == 2


async def test_other_source_or_period_is_a_real_search(stand: Stand) -> None:
    stub = stand.stub
    source_id = await add_source(stub)
    other_id = await add_source(stub, OTHER_URL)
    await wait_final(stub, (await start(stub, [source_id])).id)

    by_source = await start(stub, [other_id])
    assert by_source.status == pb.SEARCH_STATUS_QUEUED and not by_source.HasField("cache")
    by_period = await start(stub, [source_id], days=7)
    assert by_period.status == pb.SEARCH_STATUS_QUEUED and not by_period.HasField("cache")
    await wait_final(stub, by_source.id)
    await wait_final(stub, by_period.id)


async def test_fresh_runs_the_pipeline(stand: Stand) -> None:
    stub = stand.stub
    source_id = await add_source(stub)
    first = await wait_final(stub, (await start(stub, [source_id])).id)
    calls = len(stand.collector.calls)

    fresh = await start(stub, [source_id], fresh=True)
    assert fresh.status == pb.SEARCH_STATUS_QUEUED and not fresh.HasField("cache")
    done = await wait_final(stub, fresh.id)
    assert len(stand.collector.calls) == calls + 1
    # свежий поиск сам стал подборкой для следующих
    again = await start(stub, [source_id])
    assert again.cache.from_search_id == done.id != first.id


async def test_failed_and_cancelled_are_not_cached(stand: Stand) -> None:
    stub = stand.stub
    source_id = await add_source(stub)
    stand.collector.failing["-2034"] = "PLATFORM_UNAVAILABLE"
    failed = await wait_final(stub, (await start(stub, [source_id])).id)
    assert failed.status == pb.SEARCH_STATUS_FAILED
    assert stand.redis.ready() == {}  # type: ignore[attr-defined]

    del stand.collector.failing["-2034"]
    stand.collector.delay = 5
    running = await start(stub, [source_id])
    await stub.CancelSearch(pb.CancelSearchRequest(context=CTX, search_id=running.id))
    cancelled = await wait_final(stub, running.id)
    assert cancelled.status == pb.SEARCH_STATUS_CANCELLED
    assert stand.redis.ready() == {}  # type: ignore[attr-defined]

    stand.collector.delay = 0
    again = await start(stub, [source_id])
    assert again.status == pb.SEARCH_STATUS_QUEUED and not again.HasField("cache")
    await wait_final(stub, again.id)


async def test_source_search_gone_means_real_search(stand: Stand) -> None:
    """В Redis ключ есть, а поиска нет (база пересоздана) — обычный поиск, без ошибки."""
    stub = stand.stub
    source_id = await add_source(stub)
    first = await wait_final(stub, (await start(stub, [source_id])).id)
    del stand.uow.searches.store[uuid.UUID(first.id)]

    again = await start(stub, [source_id])
    assert again.status == pb.SEARCH_STATUS_QUEUED and not again.HasField("cache")
    await wait_final(stub, again.id)


async def test_redis_down_search_still_works() -> None:
    s, runner, server = await make_stand(BrokenRedis())
    try:
        source_id = await add_source(s.stub)
        with structlog.testing.capture_logs() as logs:
            first = await wait_final(s.stub, (await start(s.stub, [source_id])).id)
            again = await wait_final(s.stub, (await start(s.stub, [source_id])).id)
        assert first.status == again.status == pb.SEARCH_STATUS_COMPLETED
        assert not again.HasField("cache")
        warnings = [e for e in logs if e["event"] == "cache unavailable"]
        assert warnings and all(e["log_level"] == "warning" for e in warnings)
    finally:
        await runner.cancel_all()
        await server.stop(grace=None)


async def test_cache_disabled_works_as_before() -> None:
    s, runner, server = await make_stand(None)
    try:
        source_id = await add_source(s.stub)
        await wait_final(s.stub, (await start(s.stub, [source_id])).id)
        again = await start(s.stub, [source_id])
        assert again.status == pb.SEARCH_STATUS_QUEUED and not again.HasField("cache")
        await wait_final(s.stub, again.id)
    finally:
        await runner.cancel_all()
        await server.stop(grace=None)


async def test_cache_logs_hit_miss_store_without_query_text(stand: Stand) -> None:
    stub = stand.stub
    source_id = await add_source(stub)
    with structlog.testing.capture_logs() as logs:
        await wait_final(stub, (await start(stub, [source_id])).id)
        await start(stub, [source_id])
    events = [e["event"] for e in logs if str(e.get("key", "")).startswith("mp:search:v2:")]
    assert events == ["cache miss", "cache store", "cache hit"]
    assert not any("дорожного" in str(e) for e in logs if e["event"].startswith("cache"))


def test_cacheable_statuses() -> None:
    from search_service.applications.handlers.pipeline import CACHEABLE_STATUSES

    assert CACHEABLE_STATUSES == {SearchStatus.COMPLETED, SearchStatus.PARTIAL}


# ---------- такой же поиск уже идёт (P2) ----------


async def test_repeat_while_running_waits_and_gets_copy(stand: Stand) -> None:
    """Повтор (другие пробелы и порядок слов) во время идущего поиска не запускает второй сбор:
    стоит в очереди с пометкой и после финала оригинала получает копию под своим id."""
    stub = stand.stub
    source_id = await add_source(stub)
    stand.collector.delay = 0.3
    first = await start(stub, [source_id])
    repeat = await start(stub, [source_id], query="движения дорожного  Безопасность")
    assert repeat.id != first.id
    assert repeat.status == pb.SEARCH_STATUS_QUEUED and not repeat.HasField("cache")
    assert any("уже идёт" in w for w in repeat.warnings)

    done_first = await wait_final(stub, first.id)
    done_repeat = await wait_final(stub, repeat.id)
    assert done_first.status == done_repeat.status == pb.SEARCH_STATUS_COMPLETED
    assert done_repeat.cache.from_search_id == first.id
    assert done_repeat.counts.total == done_first.counts.total == 2
    assert not any("уже идёт" in w for w in done_repeat.warnings)
    assert [c for c in stand.collector.calls if c.startswith("collect:")] == ["collect:vk:-2034"]
    # отметка «идёт» снята, готовая подборка в кэше
    assert not any(k.startswith("mp:search:running:") for k in stand.redis.data)  # type: ignore[attr-defined]
    assert len(stand.redis.ready()) == 1  # type: ignore[attr-defined]


async def test_repeat_runs_itself_when_original_cancelled(stand: Stand) -> None:
    stub = stand.stub
    source_id = await add_source(stub)
    stand.collector.delay = 5
    first = await start(stub, [source_id])
    repeat = await start(stub, [source_id])
    assert repeat.status == pb.SEARCH_STATUS_QUEUED
    stand.collector.delay = 0
    await stub.CancelSearch(pb.CancelSearchRequest(context=CTX, search_id=first.id))

    done = await wait_final(stub, repeat.id)
    assert done.status == pb.SEARCH_STATUS_COMPLETED and not done.HasField("cache")
    assert done.counts.total == 2
    assert not any("уже идёт" in w for w in done.warnings)


async def test_fresh_does_not_join_running(stand: Stand) -> None:
    stub = stand.stub
    source_id = await add_source(stub)
    stand.collector.delay = 0.3
    first = await start(stub, [source_id])
    fresh = await start(stub, [source_id], fresh=True)
    assert not any("уже идёт" in w for w in fresh.warnings)
    await wait_final(stub, first.id)
    done = await wait_final(stub, fresh.id)
    assert not done.HasField("cache")
    assert len([c for c in stand.collector.calls if c.startswith("collect:")]) == 2


async def test_cancel_repeat_keeps_original_running(stand: Stand) -> None:
    stub = stand.stub
    source_id = await add_source(stub)
    stand.collector.delay = 0.3
    first = await start(stub, [source_id])
    repeat = await start(stub, [source_id])
    await stub.CancelSearch(pb.CancelSearchRequest(context=CTX, search_id=repeat.id))
    assert (await wait_final(stub, repeat.id)).status == pb.SEARCH_STATUS_CANCELLED
    assert (await wait_final(stub, first.id)).status == pb.SEARCH_STATUS_COMPLETED


async def test_stale_running_mark_is_ignored(stand: Stand) -> None:
    """Отметка «идёт» есть, а поиск уже закончился (не снялась) — обычный поиск или кэш."""
    stub = stand.stub
    source_id = await add_source(stub)
    first = await wait_final(stub, (await start(stub, [source_id])).id)
    stand.redis.data.clear()  # type: ignore[attr-defined]
    k = search_cache_key(
        query="безопасность дорожного движения",
        period_from=(TODAY - timedelta(days=30)).date(),
        period_to=TODAY.date(),
        mode=SearchMode.SELECTED,
        platforms=[],
        source_ids=[uuid.UUID(source_id)],
    )
    await RedisSearchCache(stand.redis, ttl_seconds=60).put_running(k, uuid.UUID(first.id))  # type: ignore[arg-type]
    again = await start(stub, [source_id])
    assert not any("уже идёт" in w for w in again.warnings)
    await wait_final(stub, again.id)
