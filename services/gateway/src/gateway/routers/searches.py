"""Поисковые задачи → search_service. Фронт опрашивает GET /searches/{id} раз в 1.5 с."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from search.v1 import search_service_pb2 as pb

from gateway.dependencies import Clients, Ctx
from gateway.schemas.common import ERRORS
from gateway.schemas.enums import MODE_TO_PROTO, PLATFORM_TO_PROTO
from gateway.schemas.searches import (
    RetryIn,
    SearchCreateIn,
    SearchOut,
    SearchSummaryOut,
    SearchSummaryPageOut,
)

router = APIRouter(prefix="/api/v1/searches", tags=["searches"], responses=ERRORS)


@router.post("", status_code=status.HTTP_202_ACCEPTED, operation_id="startSearch")
async def start_search(body: SearchCreateIn, ctx: Ctx, clients: Clients) -> SearchOut:
    result = await clients.search.StartSearch(
        pb.StartSearchRequest(
            context=ctx,
            query=body.query,
            period_from=body.period_from.isoformat(),
            period_to=body.period_to.isoformat(),
            mode=MODE_TO_PROTO[body.mode],
            platforms=[PLATFORM_TO_PROTO[p] for p in body.platforms],
            source_ids=[str(s) for s in body.source_ids],
            fresh=body.fresh,
        )
    )
    return SearchOut.from_proto(result.search)


@router.get("", operation_id="listSearches")
async def list_searches(
    ctx: Ctx,
    clients: Clients,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchSummaryPageOut:
    result = await clients.search.ListSearches(
        pb.ListSearchesRequest(context=ctx, limit=limit, offset=offset)
    )
    return SearchSummaryPageOut(
        items=[SearchSummaryOut.from_proto(s) for s in result.searches],
        has_more=result.has_more,
    )


@router.get("/{search_id}", operation_id="getSearch")
async def get_search(search_id: UUID, ctx: Ctx, clients: Clients) -> SearchOut:
    result = await clients.search.GetSearch(
        pb.GetSearchRequest(context=ctx, search_id=str(search_id))
    )
    return SearchOut.from_proto(result.search)


@router.post("/{search_id}/retry", status_code=status.HTTP_202_ACCEPTED, operation_id="retrySearch")
async def retry_search(
    search_id: UUID, ctx: Ctx, clients: Clients, body: RetryIn | None = None
) -> SearchOut:
    result = await clients.search.RetrySearch(
        pb.RetrySearchRequest(
            context=ctx,
            search_id=str(search_id),
            target_ids=body.target_ids if body else [],
        )
    )
    return SearchOut.from_proto(result.search)


@router.post("/{search_id}/cancel", operation_id="cancelSearch")
async def cancel_search(search_id: UUID, ctx: Ctx, clients: Clients) -> SearchOut:
    result = await clients.search.CancelSearch(
        pb.CancelSearchRequest(context=ctx, search_id=str(search_id))
    )
    return SearchOut.from_proto(result.search)
