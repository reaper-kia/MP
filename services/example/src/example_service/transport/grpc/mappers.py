from uuid import UUID

from contracts.example.v1 import example_pb2 as pb
from example_service.application.dto import ItemView
from example_service.domain.item import ItemStatus
from platform_common.errors import ValidationError
from platform_common.time import to_timestamp

STATUS_TO_PB = {ItemStatus.OPEN: pb.ITEM_STATUS_OPEN, ItemStatus.DONE: pb.ITEM_STATUS_DONE}
STATUS_FROM_PB: dict[int, ItemStatus] = {int(v): k for k, v in STATUS_TO_PB.items()}


def status_from_pb(value: int) -> ItemStatus | None:
    """UNSPECIFIED → None ("не менять"/"без фильтра")."""
    if value == pb.ITEM_STATUS_UNSPECIFIED:
        return None
    try:
        return STATUS_FROM_PB[value]
    except KeyError as exc:
        raise ValidationError.field("status", "unknown_value") from exc


def parse_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValidationError.field(field, "invalid_uuid") from exc


def item_to_pb(item: ItemView) -> pb.Item:
    return pb.Item(
        id=str(item.id),
        owner_id=str(item.owner_id),
        owner_name=item.owner_name or "",
        title=item.title,
        description=item.description,
        status=STATUS_TO_PB[item.status],
        created_at=to_timestamp(item.created_at),
        updated_at=to_timestamp(item.updated_at),
    )
