"""proto → запрос → mediator → proto. Логики и try/except здесь нет (ошибки — @grpc_errors)."""

from collector.v1 import collector_service_pb2 as pb
from collector.v1 import collector_service_pb2_grpc as pb_grpc

from collector_service.applications.mediator import Mediator
from collector_service.applications.queries.platforms import GetPlatformsQuery, SearchPlatformQuery
from collector_service.applications.queries.sources import (
    CollectFromSourceQuery,
    ResolveSourceQuery,
)
from collector_service.transport.grpc.errors import Context, grpc_errors
from collector_service.transport.grpc.mappers import (
    collect_to_proto,
    context_from_proto,
    period_from_proto,
    platform_from_proto,
    platform_info_to_proto,
    source_to_proto,
)


class CollectorServicer(pb_grpc.CollectorServiceServicer):
    def __init__(self, mediator: Mediator) -> None:
        self._mediator = mediator

    @grpc_errors
    async def GetPlatforms(
        self, request: pb.GetPlatformsRequest, context: Context
    ) -> pb.GetPlatformsResponse:
        platforms = await self._mediator.send(
            GetPlatformsQuery(ctx=context_from_proto(request.context, context.time_remaining()))
        )
        return pb.GetPlatformsResponse(platforms=[platform_info_to_proto(p) for p in platforms])

    @grpc_errors
    async def ResolveSource(
        self, request: pb.ResolveSourceRequest, context: Context
    ) -> pb.ResolveSourceResponse:
        source = await self._mediator.send(
            ResolveSourceQuery(
                ctx=context_from_proto(request.context, context.time_remaining()), url=request.url
            )
        )
        return pb.ResolveSourceResponse(source=source_to_proto(source))

    @grpc_errors
    async def CollectFromSource(
        self, request: pb.CollectFromSourceRequest, context: Context
    ) -> pb.CollectFromSourceResponse:
        result = await self._mediator.send(
            CollectFromSourceQuery(
                ctx=context_from_proto(request.context, context.time_remaining()),
                platform=platform_from_proto(request.platform),
                source_external_id=request.source_external_id,
                period=period_from_proto(request.period, request.HasField("period")),
                keywords=list(request.keywords),
                max_posts=request.max_posts,
            )
        )
        posts, truncated, warnings = collect_to_proto(result)
        return pb.CollectFromSourceResponse(posts=posts, truncated=truncated, warnings=warnings)

    @grpc_errors
    async def SearchPlatform(
        self, request: pb.SearchPlatformRequest, context: Context
    ) -> pb.SearchPlatformResponse:
        result = await self._mediator.send(
            SearchPlatformQuery(
                ctx=context_from_proto(request.context, context.time_remaining()),
                platform=platform_from_proto(request.platform),
                queries=list(request.queries),
                period=period_from_proto(request.period, request.HasField("period")),
                region_terms=list(request.region_terms),
                max_posts=request.max_posts,
            )
        )
        posts, truncated, warnings = collect_to_proto(result)
        return pb.SearchPlatformResponse(posts=posts, truncated=truncated, warnings=warnings)
