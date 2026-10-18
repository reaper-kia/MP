from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from example_service.domain.item import Item, ItemStatus


@dataclass(frozen=True, slots=True)
class ItemView:
    id: UUID
    owner_id: UUID
    title: str
    description: str
    status: ItemStatus
    created_at: datetime
    updated_at: datetime
    owner_name: str | None = None

    @classmethod
    def from_item(cls, item: Item, owner_name: str | None = None) -> "ItemView":
        return cls(
            id=item.id,
            owner_id=item.owner_id,
            title=item.title,
            description=item.description,
            status=item.status,
            created_at=item.created_at,
            updated_at=item.updated_at,
            owner_name=owner_name,
        )


@dataclass(frozen=True, slots=True)
class ItemPage:
    items: list[ItemView]
    next_cursor: str
