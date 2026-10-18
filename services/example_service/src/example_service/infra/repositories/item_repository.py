from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from example_service.applications.ports.repositories import ItemRepository
from example_service.domain.entities import Item, ItemStatus
from example_service.domain.value_objects import ItemTitle
from example_service.infra.database.models import ItemModel


class SQLAlchemyItemRepository(ItemRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, item: Item) -> None:
        self._session.add(self._to_model(item))
        await self._session.flush()

    async def save(self, item: Item) -> None:
        model = await self._session.get(ItemModel, item.id)
        if model is None:
            return
        model.title = item.title.value
        model.description = item.description
        model.status = item.status.value
        model.updated_at = item.updated_at

    async def delete(self, item_id: UUID) -> None:
        await self._session.execute(delete(ItemModel).where(ItemModel.id == item_id))

    async def get_by_id(self, item_id: UUID) -> Item | None:
        model = await self._session.get(ItemModel, item_id)
        return self._to_domain(model) if model else None

    async def list_by_owner(self, owner_id: UUID | None, *, limit: int, offset: int) -> list[Item]:
        stmt = select(ItemModel)
        if owner_id is not None:
            stmt = stmt.where(ItemModel.owner_id == owner_id)
        stmt = stmt.order_by(ItemModel.created_at.desc(), ItemModel.id).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    @staticmethod
    def _to_model(item: Item) -> ItemModel:
        return ItemModel(
            id=item.id,
            owner_id=item.owner_id,
            title=item.title.value,
            description=item.description,
            status=item.status.value,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _to_domain(model: ItemModel) -> Item:
        return Item(
            id=model.id,
            owner_id=model.owner_id,
            title=ItemTitle(model.title),
            description=model.description,
            status=ItemStatus(model.status),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
