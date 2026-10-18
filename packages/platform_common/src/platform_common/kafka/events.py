from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from platform_common.time import utcnow


@dataclass(frozen=True, slots=True)
class Event:
    """Конверт события. type — "<domain>.<event>.v<N>", payload — только JSON-типы."""

    type: str
    payload: dict[str, Any]
    producer: str
    id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "type": self.type,
            "producer": self.producer,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        return cls(
            id=UUID(data["id"]),
            type=data["type"],
            producer=data.get("producer", ""),
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
            payload=dict(data.get("payload") or {}),
        )
