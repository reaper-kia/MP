"""gRPC-клиент к collector_service: proto ⇄ DTO порта, ошибки → UpstreamError."""

from collections.abc import Sequence

import grpc
from collector.v1 import collector_service_pb2 as pb
from collector.v1 import collector_service_pb2_grpc as pb_grpc

from search_service.applications.context import RequestContext
from search_service.applications.ports.collector import (
    CollectorClient,
    CollectResult,
    PlatformInfo,
    PostMetrics,
    RawPost,
    SourceInfo,
)
from search_service.domain.enums import Platform
from search_service.domain.value_objects import UtcPeriod
from search_service.infra.clients.common import (
    PLATFORM_FROM_PROTO,
    PLATFORM_TO_PROTO,
    context_to_proto,
    from_timestamp,
    period_to_proto,
    upstream_error,
)

HEALTH_FROM_PROTO: dict[int, str] = {
    pb.PLATFORM_HEALTH_OK: "ok",
    pb.PLATFORM_HEALTH_DEGRADED: "degraded",
    pb.PLATFORM_HEALTH_UNAVAILABLE: "unavailable",
}


class GrpcCollectorClient(CollectorClient):
    def __init__(
        self, channel: grpc.aio.Channel, resolve_timeout: float, collect_timeout: float
    ) -> None:
        self._stub = pb_grpc.CollectorServiceStub(channel)
        self._resolve_timeout = resolve_timeout
        self._collect_timeout = collect_timeout

    async def get_platforms(self, ctx: RequestContext) -> list[PlatformInfo]:
        try:
            response: pb.GetPlatformsResponse = await self._stub.GetPlatforms(
                pb.GetPlatformsRequest(context=context_to_proto(ctx)),
                timeout=self._resolve_timeout,
            )
        except grpc.aio.AioRpcError as e:
            raise upstream_error("collector", e) from e
        return [
            PlatformInfo(
                platform=PLATFORM_FROM_PROTO[p.platform],
                title=p.title,
                source_mode_supported=p.source_mode_supported,
                global_mode_supported=p.global_mode_supported,
                health=HEALTH_FROM_PROTO.get(p.health, "unavailable"),
                note=p.note,
            )
            for p in response.platforms
            if p.platform in PLATFORM_FROM_PROTO
        ]

    async def resolve_source(self, ctx: RequestContext, url: str) -> SourceInfo:
        try:
            response: pb.ResolveSourceResponse = await self._stub.ResolveSource(
                pb.ResolveSourceRequest(context=context_to_proto(ctx), url=url),
                timeout=self._resolve_timeout,
            )
        except grpc.aio.AioRpcError as e:
            raise upstream_error("collector", e) from e
        s = response.source
        return SourceInfo(
            platform=PLATFORM_FROM_PROTO[s.platform],
            external_id=s.external_id,
            screen_name=s.screen_name,
            url=s.url,
            name=s.name,
            city=s.city if s.HasField("city") else None,
            members_count=s.members_count if s.HasField("members_count") else None,
            is_closed=s.is_closed,
        )

    async def collect_from_source(
        self,
        ctx: RequestContext,
        platform: Platform,
        source_external_id: str,
        period: UtcPeriod,
        keywords: Sequence[str] = (),
        max_posts: int = 0,
    ) -> CollectResult:
        request = pb.CollectFromSourceRequest(
            context=context_to_proto(ctx),
            platform=PLATFORM_TO_PROTO[platform],
            source_external_id=source_external_id,
            period=period_to_proto(period),
            keywords=list(keywords),
            max_posts=max_posts,
        )
        try:
            response: pb.CollectFromSourceResponse = await self._stub.CollectFromSource(
                request, timeout=self._collect_timeout
            )
        except grpc.aio.AioRpcError as e:
            raise upstream_error("collector", e) from e
        return CollectResult(
            posts=[_post(p) for p in response.posts if p.platform in PLATFORM_FROM_PROTO],
            truncated=response.truncated,
            warnings=list(response.warnings),
        )

    async def search_platform(
        self,
        ctx: RequestContext,
        platform: Platform,
        queries: Sequence[str],
        period: UtcPeriod,
        region_terms: Sequence[str] = (),
        max_posts: int = 0,
    ) -> CollectResult:
        request = pb.SearchPlatformRequest(
            context=context_to_proto(ctx),
            platform=PLATFORM_TO_PROTO[platform],
            queries=list(queries),
            period=period_to_proto(period),
            region_terms=list(region_terms),
            max_posts=max_posts,
        )
        try:
            response: pb.SearchPlatformResponse = await self._stub.SearchPlatform(
                request, timeout=self._collect_timeout
            )
        except grpc.aio.AioRpcError as e:
            raise upstream_error("collector", e) from e
        return CollectResult(
            posts=[_post(p) for p in response.posts if p.platform in PLATFORM_FROM_PROTO],
            truncated=response.truncated,
            warnings=list(response.warnings),
        )


def _post(p: pb.RawPost) -> RawPost:
    m = p.metrics
    return RawPost(
        platform=PLATFORM_FROM_PROTO[p.platform],
        source_external_id=p.source_external_id,
        source_name=p.source_name,
        source_url=p.source_url,
        post_external_id=p.post_external_id,
        url=p.url,
        text=p.text,
        title=p.title if p.HasField("title") else None,
        published_at=from_timestamp(p.published_at) if p.HasField("published_at") else None,
        metrics=PostMetrics(
            views=m.views if m.HasField("views") else None,
            likes=m.likes if m.HasField("likes") else None,
            reposts=m.reposts if m.HasField("reposts") else None,
            comments=m.comments if m.HasField("comments") else None,
        ),
        is_repost=p.is_repost,
        repost_of_url=p.repost_of_url if p.HasField("repost_of_url") else None,
        fetched_at=from_timestamp(p.fetched_at),
    )
