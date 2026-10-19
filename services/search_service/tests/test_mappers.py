"""Мапперы read model → proto: «нет данных» = поле не заполнено (HasField == False)."""

from datetime import UTC, date, datetime
from uuid import uuid4

from search.v1 import search_service_pb2 as pb

from search_service.applications.results.read_models import (
    ErrorInfoView,
    ExcerptPartView,
    MetricsView,
    RegionView,
    ResultSourceView,
    ResultView,
    SearchCountsView,
    SearchParamsView,
    SearchProgressView,
    SearchTargetView,
    SearchView,
)
from search_service.domain.enums import (
    DateStatus,
    Platform,
    Relevance,
    SearchMode,
    SearchStage,
    SearchStatus,
    TargetKind,
    TargetStatus,
    TitleSource,
)
from search_service.transport.grpc.mappers import result_to_proto, search_to_proto

NOW = datetime(2026, 10, 19, 5, 0, tzinfo=UTC)


def test_result_without_date_and_metrics() -> None:
    view = ResultView(
        id=uuid4(),
        publication_id=uuid4(),
        platform=Platform.VK,
        source=ResultSourceView(None, "Новости", "https://vk.com/n", True),
        url="https://vk.com/wall-1_2",
        title="Начало поста",
        title_source=TitleSource.POST_START,
        excerpt="текст",
        excerpt_parts=[ExcerptPartView("текст", True)],
        published_at=None,
        date_status=DateStatus.UNKNOWN,
        relevance=Relevance.IRRELEVANT,
        score=0.1,
        explanation="нет",
        region=RegionView(True, False, ""),
        sentiment=None,
        group_id=None,
        group_size=1,
        metrics=MetricsView(views=10),
        excluded=False,
        found_by_target_id=uuid4(),
    )
    message = result_to_proto(view)
    assert not message.HasField("published_at") and not message.HasField("group_id")
    assert not message.source.HasField("source_id")
    assert message.metrics.HasField("views") and not message.metrics.HasField("likes")
    assert message.relevance == pb.RELEVANCE_IRRELEVANT
    assert message.sentiment == pb.SENTIMENT_UNSPECIFIED
    assert message.date_status == pb.DATE_STATUS_UNKNOWN


def test_search_optional_fields() -> None:
    target = SearchTargetView(
        id=uuid4(),
        kind=TargetKind.PLATFORM_SEARCH,
        platform=Platform.OK,
        source_id=None,
        name="Поиск по всем OK",
        url=None,
        status=TargetStatus.FAILED,
        fetched=0,
        matched=0,
        error=ErrorInfoView("TIMEOUT", "Одноклассники не ответили"),
        attempts=1,
        finished_at=NOW,
    )
    view = SearchView(
        id=uuid4(),
        status=SearchStatus.PARTIAL,
        stage=SearchStage.DONE,
        progress=SearchProgressView(1, 1, 100),
        params=SearchParamsView(
            "БДД", None, date(2026, 10, 1), date(2026, 10, 19), SearchMode.GLOBAL, [Platform.OK], []
        ),
        query_analysis=None,
        targets=[target],
        counts=SearchCountsView(),
        warnings=[],
        created_at=NOW,
        started_at=NOW,
        finished_at=None,
    )
    message = search_to_proto(view)
    assert message.params.period_from == "2026-10-01"
    assert not message.HasField("query_analysis") and not message.HasField("finished_at")
    t = message.targets[0]
    assert not t.HasField("source_id") and not t.HasField("url")
    assert t.error.code == "TIMEOUT" and t.status == pb.TARGET_STATUS_FAILED
