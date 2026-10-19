from collector.v1 import collector_service_pb2 as pb
from collector.v1 import collector_service_pb2_grpc as pb_grpc

from collector_service.service import CollectorService
from collector_service.transport.grpc.errors import Context, grpc_errors
from collector_service.transport.grpc.mappers import (
    collect_to_proto,
    period_from_proto,
    platform_from_proto,
    platform_info_to_proto,
    source_to_proto,
)


class CollectorServicer(pb_grpc.CollectorServiceServicer):
    """Только перевод proto ⇄ сервис. Логики здесь нет."""

    def __init__(self, service: CollectorService) -> None:
        self._service = service

    @grpc_errors
    async def GetPlatforms(
        self, request: pb.GetPlatformsRequest, context: Context
    ) -> pb.GetPlatformsResponse:
        platforms = await self._service.get_platforms()
        return pb.GetPlatformsResponse(platforms=[platform_info_to_proto(p) for p in platforms])

    @grpc_errors
    async def ResolveSource(
        self, request: pb.ResolveSourceRequest, context: Context
    ) -> pb.ResolveSourceResponse:
        source = await self._service.resolve_source(request.url)
        return pb.ResolveSourceResponse(source=source_to_proto(source))

    @grpc_errors
    async def CollectFromSource(
        self, request: pb.CollectFromSourceRequest, context: Context
    ) -> pb.CollectFromSourceResponse:
        result = await self._service.collect_from_source(
            platform=platform_from_proto(request.platform),
            source_external_id=request.source_external_id,
            period=period_from_proto(request.period, request.HasField("period")),
            keywords=list(request.keywords),
            max_posts=request.max_posts,
        )
        posts, truncated, warnings = collect_to_proto(result)
        return pb.CollectFromSourceResponse(posts=posts, truncated=truncated, warnings=warnings)

    @grpc_errors
    async def SearchPlatform(
        self, request: pb.SearchPlatformRequest, context: Context
    ) -> pb.SearchPlatformResponse:
        result = await self._service.search_platform(
            platform=platform_from_proto(request.platform),
            queries=list(request.queries),
            period=period_from_proto(request.period, request.HasField("period")),
            region_terms=list(request.region_terms),
            max_posts=request.max_posts,
        )
        posts, truncated, warnings = collect_to_proto(result)
        return pb.SearchPlatformResponse(posts=posts, truncated=truncated, warnings=warnings)
