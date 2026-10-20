"""gRPC-клиент к collector_service: proto ⇄ DTO порта, ошибки → UpstreamError.

Реализует порт applications/ports/collector_client.py (им пользуется пайплайн B2).
"""

from datetime import datetime

import grpc
from collector.v1 import collector_service_pb2 as pb
from collector.v1 import collector_service_pb2_grpc as pb_grpc
from common.v1 import platform_pb2

from search_service.applications.exceptions import UpstreamError
from search_service.applications.ports.collector_client import (
    CollectorClient,
    CollectResult,
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

# GetPlatforms: collector ждёт каждую площадку не дольше 3.5 с и отвечает из кэша
PLATFORMS_TIMEOUT = 5.0


def _platform_to_proto(platform: str) -> platform_pb2.Platform:
    try:
        return PLATFORM_TO_PROTO[Platform(platform)]
    except ValueError as e:
        message = f"Неизвестная площадка {platform}"
        raise UpstreamError("collector", "VALIDATION_ERROR", message) from e


class GrpcCollectorClient(CollectorClient):
    def __init__(
        self, channel: grpc.aio.Channel, resolve_timeout: float, collect_timeout: float
    ) -> None:
        self._stub = pb_grpc.CollectorServiceStub(channel)
        self._resolve_timeout = resolve_timeout
        self._collect_timeout = collect_timeout

    async def resolve_source(self, url: str) -> SourceInfo:
        try:
            response: pb.ResolveSourceResponse = await self._stub.ResolveSource(
                pb.ResolveSourceRequest(context=context_to_proto(), url=url),
                timeout=self._resolve_timeout,
            )
        except grpc.aio.AioRpcError as e:
            raise upstream_error("collector", e) from e
        s = response.source
        return SourceInfo(
            platform=PLATFORM_FROM_PROTO[s.platform].value,
            external_id=s.external_id,
            screen_name=s.screen_name,
            url=s.url,
            name=s.name,
            city=s.city if s.HasField("city") else None,
            members_count=s.members_count if s.HasField("members_count") else None,
            is_closed=s.is_closed,
        )

    async def global_platforms(self) -> set[str]:
        try:
            response: pb.GetPlatformsResponse = await self._stub.GetPlatforms(
                pb.GetPlatformsRequest(context=context_to_proto()), timeout=PLATFORMS_TIMEOUT
            )
        except grpc.aio.AioRpcError as e:
            raise upstream_error("collector", e) from e
        return {
            PLATFORM_FROM_PROTO[p.platform].value
            for p in response.platforms
            if p.platform in PLATFORM_FROM_PROTO
            and p.global_mode_supported
            and p.health != pb.PLATFORM_HEALTH_UNAVAILABLE
        }

    async def collect_from_source(
        self,
        *,
        platform: str,
        source_external_id: str,
        start_utc: datetime,
        end_utc: datetime,
        keywords: list[str],
        max_posts: int = 300,
    ) -> CollectResult:
        request = pb.CollectFromSourceRequest(
            context=context_to_proto(),
            platform=_platform_to_proto(platform),
            source_external_id=source_external_id,
            period=period_to_proto(UtcPeriod(start=start_utc, end=end_utc)),
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
        *,
        platform: str,
        queries: list[str],
        start_utc: datetime,
        end_utc: datetime,
        region_terms: list[str],
        max_posts: int = 500,
    ) -> CollectResult:
        request = pb.SearchPlatformRequest(
            context=context_to_proto(),
            platform=_platform_to_proto(platform),
            queries=list(queries),
            period=period_to_proto(UtcPeriod(start=start_utc, end=end_utc)),
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
    metrics = {
        name: getattr(m, name)
        for name in ("views", "likes", "reposts", "comments")
        if m.HasField(name)
    }
    return RawPost(
        platform=PLATFORM_FROM_PROTO[p.platform].value,
        source_external_id=p.source_external_id,
        post_external_id=p.post_external_id,
        url=p.url,
        source_name=p.source_name,
        source_url=p.source_url,
        text=p.text,
        title=p.title if p.HasField("title") else None,
        published_at=from_timestamp(p.published_at) if p.HasField("published_at") else None,
        metrics=metrics or None,
        is_repost=p.is_repost,
        repost_of_url=p.repost_of_url if p.HasField("repost_of_url") else None,
    )
