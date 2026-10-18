from uuid import UUID

from contracts.{{name}}.v1 import {{name}}_pb2 as pb
from platform_common.errors import ValidationError
from platform_common.time import to_timestamp

from {{name}}_service.domain.{{entity}} import {{Entity}}


def parse_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValidationError.field(field, "invalid_uuid") from exc


def {{entity}}_to_pb({{entity}}: {{Entity}}) -> pb.{{Entity}}:
    return pb.{{Entity}}(
        id=str({{entity}}.id),
        owner_id=str({{entity}}.owner_id),
        title={{entity}}.title,
        created_at=to_timestamp({{entity}}.created_at),
    )
