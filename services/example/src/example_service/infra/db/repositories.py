from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from example_service.application.ports import ItemFilter
from example_service.domain.item import Item, ItemStatus
from example_service.infra.db.models import ItemModel


def _to_domain(m: ItemModel) -> Item:
    return Item(
        id=m.id,
        owner_id=m.owner_id,
        title=m.title,
        description=m.description,
        status=ItemStatus(m.status),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlAlchemyItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, item_id: UUID) -> Item | None:
        m = await self._s.get(ItemModel, item_id)
        return _to_domain(m) if m else None

    async def add(self, item: Item) -> None:
        self._s.add(
            ItemModel(
                id=item.id,
                owner_id=item.owner_id,
                title=item.title,
                description=item.description,
                status=item.status.value,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )
        await self._s.flush()

    async def update(self, item: Item) -> None:
        await self._s.execute(
            update(ItemModel)
            .where(ItemModel.id == item.id)
            .values(
                title=item.title,
                description=item.description,
                status=item.status.value,
                updated_at=item.updated_at,
            )
        )

    async def delete(self, item_id: UUID) -> None:
        await self._s.execute(delete(ItemModel).where(ItemModel.id == item_id))

    async def list(self, flt: ItemFilter, *, limit: int, offset: int) -> list[Item]:
        stmt = select(ItemModel)
        if flt.owner_id is not None:
            stmt = stmt.where(ItemModel.owner_id == flt.owner_id)
        if flt.status is not None:
            stmt = stmt.where(ItemModel.status == flt.status.value)
        stmt = stmt.order_by(ItemModel.created_at.desc(), ItemModel.id).limit(limit).offset(offset)
        return [_to_domain(m) for m in (await self._s.scalars(stmt)).all()]
