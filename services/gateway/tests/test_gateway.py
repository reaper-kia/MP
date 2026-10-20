"""Gateway без настоящих сервисов: gRPC-стабы подменены фейками."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import grpc
import httpx
import pytest
from collector.v1 import collector_service_pb2 as collector_pb
from common.v1 import platform_pb2
from google.protobuf.timestamp_pb2 import Timestamp
from ml.v1 import ml_service_pb2 as ml_pb
from search.v1 import search_service_pb2 as pb

from gateway.config import Settings
from gateway.main import create_app

SETTINGS = Settings()
SEARCH_ID = str(uuid4())


def ts(value: datetime) -> Timestamp:
    t = Timestamp()
    t.FromDatetime(value)
    return t


NOW = ts(datetime(2026, 10, 19, 5, 0, tzinfo=UTC))


def grpc_error(
    status: grpc.StatusCode, message: str, code: str | None = None
) -> grpc.aio.AioRpcError:
    trailing = grpc.aio.Metadata(("error-code", code)) if code else grpc.aio.Metadata()
    return grpc.aio.AioRpcError(status, grpc.aio.Metadata(), trailing, details=message)


def search_message() -> pb.Search:
    return pb.Search(
        id=SEARCH_ID,
        status=pb.SEARCH_STATUS_QUEUED,
        stage=pb.SEARCH_STAGE_QUEUED,
        progress=pb.SearchProgress(targets_total=1, targets_finished=0, percent=0),
        params=pb.SearchParams(
            query="Безопасность дорожного движения",
            period_from="2026-10-01",
            period_to="2026-10-19",
            mode=pb.SEARCH_MODE_GLOBAL,
            platforms=[platform_pb2.PLATFORM_VK],
        ),
        targets=[
            pb.SearchTarget(
                id="t-1",
                kind=pb.TARGET_KIND_PLATFORM_SEARCH,
                platform=platform_pb2.PLATFORM_VK,
                name="Поиск по всему VK",
                status=pb.TARGET_STATUS_PENDING,
            )
        ],
        counts=pb.SearchCounts(),
        created_at=NOW,
    )


class FakeCollector:
    async def GetPlatforms(self, req: Any, **_: Any) -> collector_pb.GetPlatformsResponse:
        return collector_pb.GetPlatformsResponse(
            platforms=[
                collector_pb.PlatformInfo(
                    platform=platform_pb2.PLATFORM_VK,
                    title="ВКонтакте",
                    source_mode_supported=True,
                    global_mode_supported=True,
                    health=collector_pb.PLATFORM_HEALTH_OK,
                ),
                collector_pb.PlatformInfo(
                    platform=platform_pb2.PLATFORM_MAX,
                    title="MAX",
                    source_mode_supported=True,
                    health=collector_pb.PLATFORM_HEALTH_DEGRADED,
                    note="Только по каналам из списка",
                ),
            ]
        )


class FakeMl:
    async def AnalyzeQuery(self, req: Any, **_: Any) -> ml_pb.AnalyzeQueryResponse:
        return ml_pb.AnalyzeQueryResponse(
            analysis=ml_pb.QueryAnalysis(
                query_type=ml_pb.QUERY_TYPE_TOPIC, summary="Тема", search_queries=[req.query]
            )
        )


class FakeSearch:
    last: Any = None

    async def StartSearch(self, req: Any, **_: Any) -> pb.StartSearchResponse:
        self.last = req
        if not req.source_ids and req.mode == pb.SEARCH_MODE_SELECTED:
            raise grpc_error(
                grpc.StatusCode.INVALID_ARGUMENT,
                "source_ids: выберите хотя бы один источник",
                "SEARCH_INVALID_PARAMS",
            )
        return pb.StartSearchResponse(search=search_message())

    async def GetSearch(self, req: Any, **_: Any) -> pb.GetSearchResponse:
        raise grpc_error(grpc.StatusCode.NOT_FOUND, "Поиск не найден", "SEARCH_NOT_FOUND")

    async def ListResults(self, req: Any, **_: Any) -> pb.ListResultsResponse:
        self.last = req
        result = pb.Result(
            id="r-1",
            publication_id="p-1",
            platform=platform_pb2.PLATFORM_VK,
            source=pb.ResultSourceRef(name="Новости", url="https://vk.com/n", is_regional=True),
            url="https://vk.com/wall-1_2",
            title="Начало поста",
            title_source=pb.TITLE_SOURCE_POST_START,
            excerpt="текст",
            excerpt_parts=[pb.ExcerptPart(text="текст", highlight=True)],
            date_status=pb.DATE_STATUS_UNKNOWN,
            relevance=pb.RELEVANCE_IRRELEVANT,
            group_size=1,
            found_by_target_id="t-1",
        )
        result.metrics.views = 10
        return pb.ListResultsResponse(results=[result], total=1)

    async def ListSources(self, req: Any, **_: Any) -> pb.ListSourcesResponse:
        raise grpc_error(grpc.StatusCode.UNIMPLEMENTED, "ListSources: B2-02", "NOT_IMPLEMENTED")

    async def ListGroups(self, req: Any, **_: Any) -> pb.ListGroupsResponse:
        self.last = req
        return pb.ListGroupsResponse()

    async def ExportSearch(self, req: Any, **_: Any) -> pb.ExportSearchResponse:
        self.last = req
        return pb.ExportSearchResponse(
            content=b"xlsx", filename="podborka.xlsx", mime_type="application/vnd.ms-excel"
        )


class FakeClients:
    def __init__(self) -> None:
        self.search = FakeSearch()
        self.collector = FakeCollector()
        self.ml = FakeMl()
        self.channels: dict[str, Any] = {}


@pytest.fixture
async def client() -> AsyncIterator[tuple[httpx.AsyncClient, FakeClients]]:
    fakes = FakeClients()
    app = create_app(SETTINGS, fakes)  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, fakes


async def test_platforms(client: Any) -> None:
    c, _ = client
    r = await c.get("/api/v1/platforms")
    assert r.status_code == 200
    vk, max_ = r.json()
    assert vk == {
        "code": "vk",
        "title": "ВКонтакте",
        "source_mode": True,
        "global_mode": True,
        "status": "ok",
        "note": None,
    }
    assert max_["status"] == "degraded" and max_["global_mode"] is False


async def test_analyze_query(client: Any) -> None:
    c, _ = client
    r = await c.post("/api/v1/query/analyze", json={"query": "ДТП Красноярск"})
    assert r.status_code == 200
    assert r.json()["query_type"] == "topic" and r.json()["clarification_hint"] is None


async def test_analyze_query_unknown_type_is_null_not_invented(client: Any) -> None:
    c, fakes = client

    async def unknown(req: Any, **_: Any) -> ml_pb.AnalyzeQueryResponse:
        return ml_pb.AnalyzeQueryResponse(
            analysis=ml_pb.QueryAnalysis(summary="Не удалось определить"), degraded=True
        )

    fakes.ml.AnalyzeQuery = unknown
    r = await c.post("/api/v1/query/analyze", json={"query": "ДТП Красноярск"})
    assert r.status_code == 200 and r.json()["query_type"] is None


async def test_start_search_202_and_mapping(client: Any) -> None:
    c, fakes = client
    body = {
        "query": "Безопасность дорожного движения",
        "period_from": "2026-10-01",
        "period_to": "2026-10-19",
        "mode": "global",
        "platforms": ["vk", "ok"],
        "source_ids": [],
    }
    r = await c.post("/api/v1/searches", json=body, headers={"X-Request-ID": "req-1"})
    assert r.status_code == 202
    data = r.json()
    assert data["status"] == "queued" and data["query_analysis"] is None
    assert data["targets"][0]["kind"] == "platform_search" and data["targets"][0]["url"] is None
    assert fakes.search.last.period_from == "2026-10-01"
    assert fakes.search.last.context.request_id == "req-1"
    assert list(fakes.search.last.platforms) == [platform_pb2.PLATFORM_VK, platform_pb2.PLATFORM_OK]
    assert fakes.search.last.context.actor_user_id == ""  # без X-Client-Id — пусто


async def test_client_id_goes_to_context_and_junk_is_dropped(client: Any) -> None:
    """X-Client-Id → actor_user_id: по нему search_service показывает только свою историю."""
    c, fakes = client
    body = {
        "query": "Безопасность дорожного движения",
        "period_from": "2026-10-01",
        "period_to": "2026-10-19",
        "mode": "global",
        "platforms": ["vk"],
    }
    browser = "3f2c7a10-8b1e-4c55-9d6f-0a1b2c3d4e5f"
    await c.post("/api/v1/searches", json=body, headers={"X-Client-Id": browser})
    assert fakes.search.last.context.actor_user_id == browser
    await c.post("/api/v1/searches", json=body, headers={"X-Client-Id": "<script>"})
    assert fakes.search.last.context.actor_user_id == ""


async def test_invalid_params_go_to_details(client: Any) -> None:
    c, _ = client
    body = {
        "query": "ДТП",
        "period_from": "2026-10-01",
        "period_to": "2026-10-19",
        "mode": "selected",
        "platforms": ["vk"],
        "source_ids": [],
    }
    r = await c.post("/api/v1/searches", json=body)
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "SEARCH_INVALID_PARAMS"
    assert error["details"] == [
        {"field": "source_ids", "message": "выберите хотя бы один источник"}
    ]


async def test_request_validation_format(client: Any) -> None:
    c, _ = client
    r = await c.post("/api/v1/searches", json={"query": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    fields = {d["field"] for d in r.json()["error"]["details"]}
    assert {"query", "period_from", "mode"} <= fields


async def test_service_code_passthrough(client: Any) -> None:
    c, _ = client
    r = await c.get(f"/api/v1/searches/{uuid4()}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "SEARCH_NOT_FOUND"


async def test_not_implemented_is_501(client: Any) -> None:
    c, _ = client
    r = await c.get("/api/v1/sources")
    assert r.status_code == 501 and r.json()["error"]["code"] == "NOT_IMPLEMENTED"


async def test_results_filter_and_nulls(client: Any) -> None:
    c, fakes = client
    r = await c.get(
        f"/api/v1/searches/{SEARCH_ID}/results?relevance=rejected&platform=vk&sort=date_desc"
    )
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["relevance"] == "rejected" and item["published_at"] is None
    assert item["sentiment"] is None and item["source"]["id"] is None
    assert item["metrics"] == {"views": 10, "likes": None, "reposts": None, "comments": None}
    sent = fakes.search.last
    assert list(sent.filter.relevance) == [pb.RELEVANCE_IRRELEVANT]
    assert sent.sort == pb.RESULT_SORT_DATE_DESC


async def test_groups_and_export_pass_target_and_date_filters(client: Any) -> None:
    c, fakes = client
    query = "target_id=t-1&target_id=t-2&date_status=unknown"
    r = await c.get(f"/api/v1/searches/{SEARCH_ID}/groups?{query}")
    assert r.status_code == 200
    assert list(fakes.search.last.filter.target_ids) == ["t-1", "t-2"]
    assert list(fakes.search.last.filter.date_status) == [pb.DATE_STATUS_UNKNOWN]

    r = await c.get(f"/api/v1/searches/{SEARCH_ID}/export?format=xlsx&{query}")
    assert r.status_code == 200
    assert list(fakes.search.last.filter.target_ids) == ["t-1", "t-2"]
    assert list(fakes.search.last.filter.date_status) == [pb.DATE_STATUS_UNKNOWN]


async def test_export_headers(client: Any) -> None:
    c, fakes = client
    r = await c.get(f"/api/v1/searches/{SEARCH_ID}/export?format=xlsx")
    assert r.status_code == 200 and r.content == b"xlsx"
    assert 'filename="podborka.xlsx"' in r.headers["content-disposition"]
    assert fakes.search.last.format == pb.EXPORT_FORMAT_XLSX


async def test_unavailable_hides_transport_details(client: Any) -> None:
    c, fakes = client

    async def down(req: Any, **_: Any) -> Any:
        raise grpc_error(grpc.StatusCode.UNAVAILABLE, "connection refused")

    fakes.collector.GetPlatforms = down
    r = await c.get("/api/v1/platforms")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "refused" not in r.json()["error"]["message"]


async def test_search_from_cache_and_fresh_flag(client: Any) -> None:
    """B2-20: fresh уходит в search_service, cache — null у обычного поиска и заполнен у копии."""
    c, fakes = client
    body = {
        "query": "Безопасность дорожного движения",
        "period_from": "2026-10-01",
        "period_to": "2026-10-19",
        "mode": "global",
        "platforms": ["vk"],
    }
    r = await c.post("/api/v1/searches", json=body)
    assert r.status_code == 202 and r.json()["cache"] is None
    assert fakes.search.last.fresh is False

    origin = str(uuid4())

    async def cached(req: Any, **_: Any) -> pb.StartSearchResponse:
        fakes.search.last = req
        message = search_message()
        message.status = pb.SEARCH_STATUS_COMPLETED
        message.cache.CopyFrom(pb.SearchCacheInfo(from_search_id=origin, created_at=NOW))
        return pb.StartSearchResponse(search=message)

    fakes.search.StartSearch = cached
    r = await c.post("/api/v1/searches", json={**body, "fresh": True})
    assert fakes.search.last.fresh is True
    assert r.json()["cache"] == {"from_search_id": origin, "created_at": "2026-10-19T05:00:00Z"}


async def test_ready_shows_redis_without_failing_status(client: Any) -> None:
    c, _ = client
    r = await c.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "services": {}, "redis": "off"}
