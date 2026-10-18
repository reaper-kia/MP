from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from platform_common.errors import ErrorDetail, NotFoundError, ValidationError
from platform_common.time import utcnow


class {{Entity}}NotFoundError(NotFoundError):
    code = "{{ENTITY}}_NOT_FOUND"
    default_message = "{{Entity}} not found"


@dataclass
class {{Entity}}:
    id: UUID
    owner_id: UUID
    title: str
    created_at: datetime

    @classmethod
    def create(cls, owner_id: UUID, title: str) -> "{{Entity}}":
        title = title.strip()
        if not 1 <= len(title) <= 200:
            raise ValidationError(details=[ErrorDetail("title", "invalid_length")])
        return cls(id=uuid4(), owner_id=owner_id, title=title, created_at=utcnow())
