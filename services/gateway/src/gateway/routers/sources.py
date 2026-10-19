"""Каталог источников → search_service."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, UploadFile, status
from search.v1 import search_service_pb2 as pb

from gateway.dependencies import AppSettings, Clients, Ctx
from gateway.schemas.common import ERRORS
from gateway.schemas.enums import PLATFORM_TO_PROTO, Platform
from gateway.schemas.sources import (
    SourceCreateIn,
    SourceImportReportOut,
    SourceOut,
    SourcePageOut,
    SourcePreviewOut,
    SourceResolveIn,
    SourceUpdateIn,
)

router = APIRouter(prefix="/api/v1/sources", tags=["sources"], responses=ERRORS)


@router.get("", operation_id="listSources")
async def list_sources(
    ctx: Ctx,
    clients: Clients,
    platform: Annotated[list[Platform] | None, Query()] = None,
    q: str = "",
    is_active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SourcePageOut:
    request = pb.ListSourcesRequest(
        context=ctx,
        platforms=[PLATFORM_TO_PROTO[p] for p in platform or []],
        q=q,
        limit=limit,
        offset=offset,
    )
    if is_active is not None:
        request.is_active = is_active
    result = await clients.search.ListSources(request)
    return SourcePageOut(
        items=[SourceOut.from_proto(s) for s in result.sources],
        total=result.total,
        has_more=result.has_more,
    )


@router.post("", status_code=status.HTTP_201_CREATED, operation_id="createSource")
async def create_source(
    body: SourceCreateIn, ctx: Ctx, clients: Clients, settings: AppSettings
) -> SourceOut:
    request = pb.CreateSourceRequest(
        context=ctx, url=body.url, is_regional=body.is_regional, notes=body.notes
    )
    if body.name:
        request.name = body.name
    result = await clients.search.CreateSource(request, timeout=settings.resolve_timeout_seconds)
    return SourceOut.from_proto(result.source)


@router.post("/resolve", operation_id="resolveSource")
async def resolve_source(
    body: SourceResolveIn, ctx: Ctx, clients: Clients, settings: AppSettings
) -> SourcePreviewOut:
    result = await clients.search.ResolveSource(
        pb.ResolveSourceRequest(context=ctx, url=body.url),
        timeout=settings.resolve_timeout_seconds,
    )
    return SourcePreviewOut.from_proto(result.preview)


@router.post("/import", operation_id="importSources")
async def import_sources(
    file: UploadFile, ctx: Ctx, clients: Clients, settings: AppSettings
) -> SourceImportReportOut:
    content = await file.read()
    result = await clients.search.ImportSources(
        pb.ImportSourcesRequest(context=ctx, xlsx=content),
        timeout=settings.import_timeout_seconds,
    )
    return SourceImportReportOut.from_proto(result)


@router.patch("/{source_id}", operation_id="updateSource")
async def update_source(
    source_id: UUID, body: SourceUpdateIn, ctx: Ctx, clients: Clients
) -> SourceOut:
    request = pb.UpdateSourceRequest(context=ctx, source_id=str(source_id))
    if body.name is not None:
        request.name = body.name
    if body.is_regional is not None:
        request.is_regional = body.is_regional
    if body.is_active is not None:
        request.is_active = body.is_active
    if body.notes is not None:
        request.notes = body.notes
    result = await clients.search.UpdateSource(request)
    return SourceOut.from_proto(result.source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="deleteSource")
async def delete_source(source_id: UUID, ctx: Ctx, clients: Clients) -> None:
    await clients.search.DeleteSource(pb.DeleteSourceRequest(context=ctx, source_id=str(source_id)))
