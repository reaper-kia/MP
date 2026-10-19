"""proto ⇄ domain/applications. Единственное место, где сервис встречается с proto."""

from datetime import UTC, datetime

from collector.v1 import collector_service_pb2 as pb
from common.v1 import common_pb2, platform_pb2
from google.protobuf.timestamp_pb2 import Timestamp

from collector_service.applications.context import RequestContext
from collector_service.applications.exceptions import InvalidRequestError
from collector_service.domain.enums import Health, Platform
from collector_service.domain.value_objects import (
    CollectResult,
    Period,
    PlatformInfo,
    RawPost,
    SourceInfo,
)

PLATFORM_TO_PROTO: dict[Platform, platform_pb2.Platform] = {
    Platform.VK: platform_pb2.PLATFORM_VK,
    Platform.OK: platform_pb2.PLATFORM_OK,
    Platform.MAX: platform_pb2.PLATFORM_MAX,
    Platform.NEWS: platform_pb2.PLATFORM_NEWS,
}
PLATFORM_FROM_PROTO: dict[int, Platform] = {v: k for k, v in PLATFORM_TO_PROTO.items()}

HEALTH_TO_PROTO: dict[Health, pb.PlatformHealth] = {
    Health.OK: pb.PLATFORM_HEALTH_OK,
    Health.DEGRADED: pb.PLATFORM_HEALTH_DEGRADED,
    Health.UNAVAILABLE: pb.PLATFORM_HEALTH_UNAVAILABLE,
}


def to_timestamp(value: datetime) -> Timestamp:
    timestamp = Timestamp()
    timestamp.FromDatetime(value)
    return timestamp


def context_from_proto(
    ctx: common_pb2.RequestContext, time_remaining: float | None = None
) -> RequestContext:
    """time_remaining — из gRPC deadline вызывающего (context.time_remaining())."""
    return RequestContext(request_id=ctx.request_id, time_remaining=time_remaining)


def platform_from_proto(value: int) -> Platform:
    platform = PLATFORM_FROM_PROTO.get(value)
    if platform is None:
        raise InvalidRequestError("Не указана площадка")
    return platform


def period_from_proto(period: platform_pb2.Period, present: bool) -> Period:
    if not present:
        raise InvalidRequestError("Не указан период")
    return Period(start=period.start.ToDatetime(tzinfo=UTC), end=period.end.ToDatetime(tzinfo=UTC))


def platform_info_to_proto(info: PlatformInfo) -> pb.PlatformInfo:
    return pb.PlatformInfo(
        platform=PLATFORM_TO_PROTO[info.platform],
        title=info.title,
        source_mode_supported=info.source_mode_supported,
        global_mode_supported=info.global_mode_supported,
        health=HEALTH_TO_PROTO[info.health],
        note=info.note,
    )


def source_to_proto(source: SourceInfo) -> pb.SourceInfo:
    message = pb.SourceInfo(
        platform=PLATFORM_TO_PROTO[source.platform],
        external_id=source.external_id,
        screen_name=source.screen_name,
        url=source.url,
        name=source.name,
        is_closed=source.is_closed,
    )
    if source.city is not None:
        message.city = source.city
    if source.members_count is not None:
        message.members_count = source.members_count
    return message


def post_to_proto(post: RawPost) -> pb.RawPost:
    message = pb.RawPost(
        platform=PLATFORM_TO_PROTO[post.platform],
        source_external_id=post.source_external_id,
        source_name=post.source_name,
        source_url=post.source_url,
        post_external_id=post.post_external_id,
        url=post.url,
        text=post.text,
        is_repost=post.is_repost,
        fetched_at=to_timestamp(post.fetched_at),
    )
    if post.title is not None:
        message.title = post.title
    if post.published_at is not None:  # нет даты — поле не заполняем (contract)
        message.published_at.CopyFrom(to_timestamp(post.published_at))
    if post.repost_of_url is not None:
        message.repost_of_url = post.repost_of_url
    m = post.metrics
    if m.views is not None:
        message.metrics.views = m.views
    if m.likes is not None:
        message.metrics.likes = m.likes
    if m.reposts is not None:
        message.metrics.reposts = m.reposts
    if m.comments is not None:
        message.metrics.comments = m.comments
    return message


def collect_to_proto(
    result: CollectResult,
) -> tuple[list[pb.RawPost], bool, list[str]]:
    return [post_to_proto(p) for p in result.posts], result.truncated, list(result.warnings)
