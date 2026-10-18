from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from platform_common.errors import ConflictError, ErrorDetail, NotFoundError, ValidationError
from platform_common.time import utcnow

MAX_TITLE = 200
MAX_DESCRIPTION = 2000


class ItemStatus(StrEnum):
    OPEN = "open"
    DONE = "done"


class ItemNotFoundError(NotFoundError):
    code = "ITEM_NOT_FOUND"
    default_message = "Item not found"


class ItemIsDoneError(ConflictError):
    code = "ITEM_IS_DONE"
    default_message = "Item is already done and can not be changed"


def _title(raw: str) -> str:
    title = raw.strip()
    if not 1 <= len(title) <= MAX_TITLE:
        raise ValidationError(details=[ErrorDetail("title", "invalid_length")])
    return title


def _description(raw: str) -> str:
    if len(raw) > MAX_DESCRIPTION:
        raise ValidationError(details=[ErrorDetail("description", "too_long")])
    return raw


@dataclass
class Item:
    id: UUID
    owner_id: UUID
    title: str
    description: str
    status: ItemStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, owner_id: UUID, title: str, description: str = "") -> "Item":
        now = utcnow()
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            title=_title(title),
            description=_description(description),
            status=ItemStatus.OPEN,
            created_at=now,
            updated_at=now,
        )

    def edit(self, *, title: str | None = None, description: str | None = None) -> None:
        if self.status is ItemStatus.DONE:
            raise ItemIsDoneError()
        if title is not None:
            self.title = _title(title)
        if description is not None:
            self.description = _description(description)
        self.updated_at = utcnow()

    def change_status(self, status: ItemStatus) -> None:
        if status is self.status:
            return
        if self.status is ItemStatus.DONE:
            raise ItemIsDoneError("Reopening is not allowed")
        self.status = status
        self.updated_at = utcnow()
