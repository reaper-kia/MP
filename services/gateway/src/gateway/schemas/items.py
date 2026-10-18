from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from contracts.example.v1 import example_pb2 as pb
from gateway.schemas.common import empty_to_none, ts

ItemStatus = Literal["open", "done"]
STATUS_TO_PB: dict[ItemStatus, pb.ItemStatus] = {
    "open": pb.ITEM_STATUS_OPEN,
    "done": pb.ITEM_STATUS_DONE,
}
STATUS_FROM_PB: dict[int, ItemStatus] = {int(v): k for k, v in STATUS_TO_PB.items()}


class ItemCreateIn(BaseModel):
    title: str = Field(max_length=200, examples=["Купить молоко"])
    description: str = Field(default="", max_length=2000)


class ItemUpdateIn(BaseModel):
    """Все поля опциональны: не передал — не меняется."""

    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: ItemStatus | None = None


class ItemOut(BaseModel):
    id: UUID
    owner_id: UUID
    owner_name: str | None
    title: str
    description: str
    status: ItemStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_pb(cls, item: pb.Item) -> "ItemOut":
        return cls(
            id=UUID(item.id),
            owner_id=UUID(item.owner_id),
            owner_name=empty_to_none(item.owner_name),
            title=item.title,
            description=item.description,
            status=STATUS_FROM_PB.get(item.status, "open"),
            created_at=ts(item.created_at),
            updated_at=ts(item.updated_at),
        )
