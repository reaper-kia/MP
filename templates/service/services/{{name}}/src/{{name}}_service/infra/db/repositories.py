from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from {{name}}_service.domain.{{entity}} import {{Entity}}
from {{name}}_service.infra.db.models import {{Entity}}Model


def _to_domain(m: {{Entity}}Model) -> {{Entity}}:
    return {{Entity}}(id=m.id, owner_id=m.owner_id, title=m.title, created_at=m.created_at)


class SqlAlchemy{{Entity}}Repository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, {{entity}}_id: UUID) -> {{Entity}} | None:
        m = await self._s.get({{Entity}}Model, {{entity}}_id)
        return _to_domain(m) if m else None

    async def add(self, {{entity}}: {{Entity}}) -> None:
        self._s.add(
            {{Entity}}Model(
                id={{entity}}.id,
                owner_id={{entity}}.owner_id,
                title={{entity}}.title,
                created_at={{entity}}.created_at,
            )
        )
        await self._s.flush()

    async def list_by_owner(self, owner_id: UUID, *, limit: int, offset: int) -> list[{{Entity}}]:
        stmt = (
            select({{Entity}}Model)
            .where({{Entity}}Model.owner_id == owner_id)
            .order_by({{Entity}}Model.created_at.desc(), {{Entity}}Model.id)
            .limit(limit)
            .offset(offset)
        )
        return [_to_domain(m) for m in (await self._s.scalars(stmt)).all()]
