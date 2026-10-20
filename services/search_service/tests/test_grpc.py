"""Сквозь gRPC: servicer → mediator → сценарии B2 → пайплайн (in-memory БД, фейки соседей)."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import grpc
import pytest
from common.v1 import common_pb2, platform_pb2
from search.v1 import search_service_pb2 as pb
from search.v1 import search_service_pb2_grpc as pb_grpc

from search_service.applications.handlers.pipeline import Pipeline
from search_service.applications.ports.collector_client import RawPost, SourceInfo
from search_service.dependencies import build_mediator, mark_interrupted_searches
from search_service.domain.entities import Search
from search_service.domain.enums import SearchMode, SearchStatus
from search_service.domain.value_objects import Period
from search_service.infra.runner import SearchRunner
from search_service.transport.grpc.server import create_server
from tests.fakes import FakeCollector, FakeMl, InMemoryUoW

CTX = common_pb2.RequestContext(request_id="test", actor_user_id="browser-a")
URL = "https://vk.com/krsk_news"
TODAY = datetime.now(UTC)
FINAL = {
    pb.SEARCH_STATUS_COMPLETED,
    pb.SEARCH_STATUS_PARTIAL,
    pb.SEARCH_STATUS_FAILED,
    pb.SEARCH_STATUS_CANCELLED,
}


def post(n: int, text: str, days_ago: int | None = 1) -> RawPost:
    return RawPost(
        platform="vk",
        source_external_id="-2034",
        post_external_id=str(n),
        url=f"https://vk.com/wall-2034_{n}",
        source_name="Красноярск: главное",
        source_url=URL,
        text=text,
        published_at=TODAY - timedelta(days=days_ago) if days_ago is not None else None,
        metrics={"views": 100 * n},
    )


@dataclass
class Stand:
    stub: pb_grpc.SearchServiceStub
    uow: InMemoryUoW
    collector: FakeCollector
    ml: FakeMl


@pytest.fixture
async def stand() -> AsyncIterator[Stand]:
    uow, collector, ml = InMemoryUoW(), FakeCollector(), FakeMl()
    # external_id (числовой id группы) не совпадает с хвостом ссылки — как у VK
    collector.sources[URL] = SourceInfo(
        platform="vk", external_id="-2034", screen_name="krsk_news", url=URL, name="Красноярск"
    )
    collector.posts[("vk", "-2034")] = [
        post(1, "ГИБДД: аварийность на дорогах края снизилась"),
        post(2, "Про погоду в Красноярске", days_ago=None),
        post(3, "Очень старая новость", days_ago=400),
    ]
    runner = SearchRunner(Pipeline(uow, collector, ml, asyncio.Semaphore(5), 10))
    server, port = await create_server(build_mediator(uow, collector, runner), "127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        yield Stand(pb_grpc.SearchServiceStub(channel), uow, collector, ml)
    finally:
        await channel.close()
        await runner.cancel_all()
        await server.stop(grace=None)


async def wait_final(stub: pb_grpc.SearchServiceStub, search_id: str) -> pb.Search:
    for _ in range(100):
        r = await stub.GetSearch(pb.GetSearchRequest(context=CTX, search_id=search_id))
        if r.search.status in FINAL:
            return r.search
        await asyncio.sleep(0.02)
    raise AssertionError("поиск не завершился")


def error_code(e: grpc.aio.AioRpcError) -> str:
    return dict(e.trailing_metadata() or ()).get("error-code", "")


async def test_full_chain(stand: Stand) -> None:
    stub = stand.stub
    preview = await stub.ResolveSource(pb.ResolveSourceRequest(context=CTX, url=URL))
    assert preview.preview.external_id == "-2034"
    assert not preview.preview.HasField("existing_source_id")

    created = await stub.CreateSource(
        pb.CreateSourceRequest(context=CTX, url=URL, is_regional=True)
    )
    source_id = created.source.id
    assert created.source.platform == platform_pb2.PLATFORM_VK

    listed = await stub.ListSources(pb.ListSourcesRequest(context=CTX))
    assert [s.id for s in listed.sources] == [source_id] and listed.total == 1

    period_from = (TODAY - timedelta(days=30)).date().isoformat()
    started = await stub.StartSearch(
        pb.StartSearchRequest(
            context=CTX,
            query="безопасность дорожного движения",
            period_from=period_from,
            period_to=TODAY.date().isoformat(),
            mode=pb.SEARCH_MODE_SELECTED,
            source_ids=[source_id],
        )
    )
    assert started.search.status == pb.SEARCH_STATUS_QUEUED
    # SELECTED: площадки берутся из источников
    assert list(started.search.params.platforms) == [platform_pb2.PLATFORM_VK]
    assert len(started.search.targets) == 1

    search = await wait_final(stub, started.search.id)
    assert search.status == pb.SEARCH_STATUS_COMPLETED, search
    assert stand.collector.calls[-1] == "collect:vk:-2034"
    target = search.targets[0]
    assert target.status == pb.TARGET_STATUS_DONE and target.fetched == 3
    assert search.counts.total == 2 and search.counts.unknown_date == 1
    assert search.query_analysis.summary.startswith("Тема:")

    results = await stub.ListResults(
        pb.ListResultsRequest(context=CTX, search_id=search.id, limit=50)
    )
    assert results.total == 2
    first = results.results[0]
    assert first.relevance == pb.RELEVANCE_DIRECT
    assert first.source.source_id == source_id
    assert "".join(p.text for p in first.excerpt_parts) == first.excerpt
    assert first.excerpt_parts[0].highlight
    assert first.found_by_target_id == target.id

    groups = await stub.ListGroups(pb.ListGroupsRequest(context=CTX, search_id=search.id))
    assert groups.total == 2 and all(g.size == 1 for g in groups.groups)

    excluded = await stub.SetExcluded(
        pb.SetExcludedRequest(
            context=CTX, search_id=search.id, result_ids=[first.id], excluded=True
        )
    )
    assert excluded.counts.total == 1 and excluded.counts.excluded == 1

    exported = await stub.ExportSearch(
        pb.ExportSearchRequest(context=CTX, search_id=search.id, format=pb.EXPORT_FORMAT_XLSX)
    )
    assert exported.content[:2] == b"PK" and exported.filename.endswith(".xlsx")

    docx = await stub.ExportSearch(
        pb.ExportSearchRequest(context=CTX, search_id=search.id, format=pb.EXPORT_FORMAT_DOCX)
    )
    assert docx.content[:2] == b"PK" and docx.filename.endswith(".docx")

    searches = await stub.ListSearches(pb.ListSearchesRequest(context=CTX))
    assert [s.id for s in searches.searches] == [search.id]
    assert not searches.searches[0].targets

    # история своя у каждого браузера: чужой и «без id» её не видят, по ссылке поиск открывается
    other = common_pb2.RequestContext(request_id="t2", actor_user_id="browser-b")
    assert not (await stub.ListSearches(pb.ListSearchesRequest(context=other))).searches
    nobody = common_pb2.RequestContext(request_id="t3")
    assert not (await stub.ListSearches(pb.ListSearchesRequest(context=nobody))).searches
    shared = await stub.GetSearch(pb.GetSearchRequest(context=other, search_id=search.id))
    assert shared.search.id == search.id


async def test_retry_only_failed_targets(stand: Stand) -> None:
    stub = stand.stub
    created = await stub.CreateSource(pb.CreateSourceRequest(context=CTX, url=URL))
    stand.collector.failing["-2034"] = "PLATFORM_UNAVAILABLE"
    started = await stub.StartSearch(
        pb.StartSearchRequest(
            context=CTX,
            query="дороги",
            period_from=(TODAY - timedelta(days=30)).date().isoformat(),
            period_to=TODAY.date().isoformat(),
            mode=pb.SEARCH_MODE_SELECTED,
            source_ids=[created.source.id],
        )
    )
    failed = await wait_final(stub, started.search.id)
    assert failed.status == pb.SEARCH_STATUS_FAILED
    assert failed.targets[0].error.code == "PLATFORM_UNAVAILABLE"
    # текст ошибки соседа доходит до пользователя как есть
    assert failed.targets[0].error.message == "тестовая ошибка PLATFORM_UNAVAILABLE"

    del stand.collector.failing["-2034"]
    retried = await stub.RetrySearch(pb.RetrySearchRequest(context=CTX, search_id=failed.id))
    assert retried.search.status in {pb.SEARCH_STATUS_QUEUED, pb.SEARCH_STATUS_RUNNING}
    done = await wait_final(stub, failed.id)
    assert done.status == pb.SEARCH_STATUS_COMPLETED
    assert done.targets[0].attempts == 2


async def test_cancel_running_search(stand: Stand) -> None:
    stub = stand.stub
    created = await stub.CreateSource(pb.CreateSourceRequest(context=CTX, url=URL))
    stand.collector.delay = 5
    started = await stub.StartSearch(
        pb.StartSearchRequest(
            context=CTX,
            query="дороги",
            period_from=(TODAY - timedelta(days=30)).date().isoformat(),
            period_to=TODAY.date().isoformat(),
            mode=pb.SEARCH_MODE_SELECTED,
            source_ids=[created.source.id],
        )
    )
    for _ in range(100):  # ждём, пока цель уйдёт в сбор
        if stand.collector.calls[-1].startswith("collect:"):
            break
        await asyncio.sleep(0.01)
    cancelled = await stub.CancelSearch(
        pb.CancelSearchRequest(context=CTX, search_id=started.search.id)
    )
    assert cancelled.search.status == pb.SEARCH_STATUS_CANCELLED
    assert cancelled.search.targets[0].status == pb.TARGET_STATUS_SKIPPED
    with pytest.raises(grpc.aio.AioRpcError) as info:  # кривой id = «не найдено»
        await stub.RetrySearch(pb.RetrySearchRequest(context=CTX, search_id="bad-id"))
    assert error_code(info.value) == "SEARCH_NOT_FOUND"


async def test_errors_have_public_codes(stand: Stand) -> None:
    stub = stand.stub
    cases = [
        (
            stub.GetSearch(pb.GetSearchRequest(context=CTX, search_id="nope")),
            grpc.StatusCode.NOT_FOUND,
            "SEARCH_NOT_FOUND",
        ),
        (
            stub.ResolveSource(pb.ResolveSourceRequest(context=CTX, url="https://vk.com/x")),
            grpc.StatusCode.NOT_FOUND,
            "SOURCE_NOT_FOUND",
        ),
        (
            stub.StartSearch(
                pb.StartSearchRequest(
                    context=CTX,
                    query="дороги",
                    period_from="2026-01-01",
                    period_to="2026-01-31",
                    mode=pb.SEARCH_MODE_SELECTED,
                )
            ),
            grpc.StatusCode.INVALID_ARGUMENT,
            "SEARCH_INVALID_PARAMS",
        ),
        (
            stub.ImportSources(pb.ImportSourcesRequest(context=CTX, xlsx=b"")),
            grpc.StatusCode.INVALID_ARGUMENT,
            "SEARCH_INVALID_PARAMS",
        ),
    ]
    for call, status, code in cases:
        with pytest.raises(grpc.aio.AioRpcError) as info:
            await call
        assert info.value.code() == status, code
        assert error_code(info.value) == code

    await stub.CreateSource(pb.CreateSourceRequest(context=CTX, url=URL))
    with pytest.raises(grpc.aio.AioRpcError) as info:
        await stub.CreateSource(pb.CreateSourceRequest(context=CTX, url=URL))
    assert error_code(info.value) == "SOURCE_ALREADY_EXISTS"


async def test_import_sources_from_xlsx(stand: Stand) -> None:
    """B2-10 через gRPC: строка из файла создаёт источник, повторная загрузка — «дубль»."""
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Ссылка", "Название", "Региональный"])
    ws.append([URL, "Главное в Красноярске", "да"])
    ws.append(["https://vk.com/unknown_group", None, None])
    buf = io.BytesIO()
    wb.save(buf)
    request = pb.ImportSourcesRequest(context=CTX, xlsx=buf.getvalue())

    first = await stand.stub.ImportSources(request)
    assert (first.created, first.duplicates) == (1, 0)
    assert [(f.row, f.error.code) for f in first.failed] == [(3, "SOURCE_NOT_FOUND")]

    second = await stand.stub.ImportSources(request)
    assert (second.created, second.duplicates) == (0, 1)
    listed = await stand.stub.ListSources(pb.ListSourcesRequest(context=CTX))
    assert [s.name for s in listed.sources] == ["Главное в Красноярске"]


async def test_start_search_details_field() -> None:
    """Сообщение SEARCH_INVALID_PARAMS — «<поле>: <текст>» (gateway кладёт в details)."""
    uow, collector = InMemoryUoW(), FakeCollector()
    runner = SearchRunner(Pipeline(uow, collector, FakeMl(), asyncio.Semaphore(1)))
    server, port = await create_server(build_mediator(uow, collector, runner), "127.0.0.1:0")
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = pb_grpc.SearchServiceStub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as info:
            await stub.StartSearch(
                pb.StartSearchRequest(
                    context=CTX,
                    query="дороги",
                    period_from="2026-01-01",
                    period_to="2026-01-31",
                    mode=pb.SEARCH_MODE_GLOBAL,
                )
            )
    await server.stop(grace=None)
    assert (info.value.details() or "").startswith("platforms:")


async def test_interrupted_searches_marked_failed() -> None:
    uow = InMemoryUoW()
    search = Search(query="q", period=Period(TODAY.date(), TODAY.date()), mode=SearchMode.GLOBAL)
    search.status = SearchStatus.RUNNING
    await uow.searches.add(search)
    assert await mark_interrupted_searches(uow) == 1
    assert search.status is SearchStatus.FAILED
    assert "перезапуском" in search.warnings[0]
