from datetime import datetime
from uuid import UUID

from contracts.{{name}}.v1 import {{name}}_pb2 as pb
from pydantic import BaseModel, Field

from gateway.schemas.common import ts


class {{Entity}}CreateIn(BaseModel):
    title: str = Field(max_length=200)


class {{Entity}}Out(BaseModel):
    id: UUID
    owner_id: UUID
    title: str
    created_at: datetime

    @classmethod
    def from_pb(cls, x: pb.{{Entity}}) -> "{{Entity}}Out":
        return cls(
            id=UUID(x.id), owner_id=UUID(x.owner_id), title=x.title, created_at=ts(x.created_at)
        )
