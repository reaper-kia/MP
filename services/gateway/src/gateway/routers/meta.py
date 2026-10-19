"""Площадки и подсказка по запросу. Ходят напрямую в collector и ml."""

from collector.v1 import collector_service_pb2 as collector_pb
from fastapi import APIRouter
from ml.v1 import ml_service_pb2 as ml_pb

from gateway.dependencies import AppSettings, Clients, Ctx
from gateway.schemas.common import ERRORS
from gateway.schemas.enums import PLATFORM_FROM_PROTO
from gateway.schemas.meta import PlatformInfoOut, QueryAnalysisOut, QueryAnalyzeIn

router = APIRouter(prefix="/api/v1", tags=["meta"], responses=ERRORS)


@router.get("/platforms", operation_id="listPlatforms")
async def list_platforms(ctx: Ctx, clients: Clients) -> list[PlatformInfoOut]:
    result = await clients.collector.GetPlatforms(collector_pb.GetPlatformsRequest(context=ctx))
    return [
        PlatformInfoOut.from_proto(p) for p in result.platforms if p.platform in PLATFORM_FROM_PROTO
    ]


@router.post("/query/analyze", operation_id="analyzeQuery")
async def analyze_query(
    body: QueryAnalyzeIn, ctx: Ctx, clients: Clients, settings: AppSettings
) -> QueryAnalysisOut:
    result = await clients.ml.AnalyzeQuery(
        ml_pb.AnalyzeQueryRequest(context=ctx, query=body.query),
        timeout=settings.analyze_timeout_seconds,
    )
    return QueryAnalysisOut.from_proto(result.analysis)
