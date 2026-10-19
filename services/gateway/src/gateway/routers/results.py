"""Подборка, исключение, экспорт → search_service."""

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Query, Response
from search.v1 import search_service_pb2 as pb

from gateway.dependencies import AppSettings, Clients, Ctx
from gateway.schemas.common import ERRORS
from gateway.schemas.enums import (
    DATE_STATUS_TO_PROTO,
    FORMAT_TO_PROTO,
    PLATFORM_TO_PROTO,
    RELEVANCE_TO_PROTO,
    SORT_TO_PROTO,
    DateStatus,
    ExportFormat,
    Platform,
    Relevance,
    ResultSort,
)
from gateway.schemas.results import (
    ExclusionIn,
    ExclusionOut,
    GroupPageOut,
    ResultGroupOut,
    ResultOut,
    ResultPageOut,
)
from gateway.schemas.searches import SearchCountsOut

router = APIRouter(prefix="/api/v1/searches/{search_id}", tags=["results"], responses=ERRORS)

RelevanceQ = Annotated[
    list[Relevance] | None,
    Query(description="По умолчанию direct+indirect+disputed; rejected — «Отсеяно системой»"),
]
PlatformQ = Annotated[list[Platform] | None, Query()]
TargetQ = Annotated[list[str] | None, Query(description="Найденное в конкретных источниках")]
DateStatusQ = Annotated[list[DateStatus] | None, Query()]


def build_filter(
    relevance: list[Relevance] | None,
    platform: list[Platform] | None,
    target_id: list[str] | None = None,
    date_status: list[DateStatus] | None = None,
    include_excluded: bool = False,
) -> pb.ResultFilter:
    return pb.ResultFilter(
        relevance=[RELEVANCE_TO_PROTO[r] for r in relevance or []],
        platforms=[PLATFORM_TO_PROTO[p] for p in platform or []],
        target_ids=list(target_id or []),
        date_status=[DATE_STATUS_TO_PROTO[d] for d in date_status or []],
        include_excluded=include_excluded,
    )


@router.get("/results", operation_id="listResults")
async def list_results(
    search_id: UUID,
    ctx: Ctx,
    clients: Clients,
    relevance: RelevanceQ = None,
    platform: PlatformQ = None,
    target_id: TargetQ = None,
    date_status: DateStatusQ = None,
    include_excluded: bool = False,
    sort: ResultSort = "relevance",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ResultPageOut:
    result = await clients.search.ListResults(
        pb.ListResultsRequest(
            context=ctx,
            search_id=str(search_id),
            filter=build_filter(relevance, platform, target_id, date_status, include_excluded),
            sort=SORT_TO_PROTO[sort],
            limit=limit,
            offset=offset,
        )
    )
    return ResultPageOut(
        items=[ResultOut.from_proto(r) for r in result.results],
        total=result.total,
        has_more=result.has_more,
    )


@router.get("/groups", operation_id="listGroups")
async def list_groups(
    search_id: UUID,
    ctx: Ctx,
    clients: Clients,
    relevance: RelevanceQ = None,
    platform: PlatformQ = None,
    target_id: TargetQ = None,
    date_status: DateStatusQ = None,
    include_excluded: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GroupPageOut:
    result = await clients.search.ListGroups(
        pb.ListGroupsRequest(
            context=ctx,
            search_id=str(search_id),
            filter=build_filter(relevance, platform, target_id, date_status, include_excluded),
            limit=limit,
            offset=offset,
        )
    )
    return GroupPageOut(
        items=[ResultGroupOut.from_proto(g) for g in result.groups],
        total=result.total,
        has_more=result.has_more,
    )


@router.post("/results/exclusion", operation_id="setExcluded")
async def set_excluded(
    search_id: UUID, body: ExclusionIn, ctx: Ctx, clients: Clients
) -> ExclusionOut:
    result = await clients.search.SetExcluded(
        pb.SetExcludedRequest(
            context=ctx,
            search_id=str(search_id),
            result_ids=body.result_ids,
            excluded=body.excluded,
        )
    )
    return ExclusionOut(counts=SearchCountsOut.from_proto(result.counts))


@router.get(
    "/export",
    operation_id="exportSearch",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}, "description": "Файл"}},
)
async def export_search(
    search_id: UUID,
    ctx: Ctx,
    clients: Clients,
    settings: AppSettings,
    format: ExportFormat,
    relevance: RelevanceQ = None,
    platform: PlatformQ = None,
    target_id: TargetQ = None,
    date_status: DateStatusQ = None,
    sort: ResultSort = "relevance",
) -> Response:
    result = await clients.search.ExportSearch(
        pb.ExportSearchRequest(
            context=ctx,
            search_id=str(search_id),
            format=FORMAT_TO_PROTO[format],
            filter=build_filter(relevance, platform, target_id, date_status),
            sort=SORT_TO_PROTO[sort],
        ),
        timeout=settings.export_timeout_seconds,
    )
    filename = result.filename or f"podborka.{format}"
    return Response(
        content=result.content,
        media_type=result.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
            )
        },
    )
