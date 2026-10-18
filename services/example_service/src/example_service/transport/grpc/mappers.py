from datetime import datetime
from uuid import UUID

from common.v1 import common_pb2
from example.v1 import example_service_pb2 as pb
from google.protobuf.timestamp_pb2 import Timestamp

from example_service.applications.context import RequestContext
from example_service.applications.exceptions import ItemNotFoundError
from example_service.applications.results.read_models import ItemReadModel

STATUS_TO_PROTO: dict[str, pb.ItemStatus] = {
    "open": pb.ITEM_STATUS_OPEN,
    "done": pb.ITEM_STATUS_DONE,
}
STATUS_FROM_PROTO: dict[int, str] = {v: k for k, v in STATUS_TO_PROTO.items()}


def to_timestamp(value: datetime) -> Timestamp:
    timestamp = Timestamp()
    timestamp.FromDatetime(value)
    return timestamp


def context_from_proto(ctx: common_pb2.RequestContext) -> RequestContext:
    return RequestContext(
        request_id=ctx.request_id,
        actor_user_id=UUID(ctx.actor_user_id) if ctx.actor_user_id else None,
        actor_role=ctx.actor_role or None,
    )


def parse_item_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as e:
        raise ItemNotFoundError("Item not found") from e


def item_to_proto(item: ItemReadModel) -> pb.Item:
    return pb.Item(
        id=str(item.id),
        owner_id=str(item.owner_id),
        owner_name=item.owner_name or "",
        title=item.title,
        description=item.description,
        status=STATUS_TO_PROTO[item.status],
        created_at=to_timestamp(item.created_at),
        updated_at=to_timestamp(item.updated_at),
    )
