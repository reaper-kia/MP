from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from example_service.domain.exceptions import ItemAlreadyDoneError
from example_service.domain.value_objects import ItemTitle


def utc_now() -> datetime:
    return datetime.now(UTC)


class ItemStatus(StrEnum):
    OPEN = "open"
    DONE = "done"


@dataclass(slots=True, kw_only=True)
class Item:
    owner_id: UUID
    title: ItemTitle
    description: str = ""

    id: UUID = field(default_factory=uuid4)
    status: ItemStatus = ItemStatus.OPEN
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(cls, owner_id: UUID, title: ItemTitle, description: str = "") -> "Item":
        return cls(owner_id=owner_id, title=title, description=description)

    def edit(self, title: ItemTitle | None = None, description: str | None = None) -> None:
        if self.status is ItemStatus.DONE:
            raise ItemAlreadyDoneError("Done item can't be changed")
        if title is not None:
            self.title = title
        if description is not None:
            self.description = description
        self.updated_at = utc_now()

    def change_status(self, status: ItemStatus) -> None:
        if status is self.status:
            return
        if self.status is ItemStatus.DONE:
            raise ItemAlreadyDoneError("Done item can't be reopened")
        self.status = status
        self.updated_at = utc_now()
