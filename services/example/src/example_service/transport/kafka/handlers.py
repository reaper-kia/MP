"""Обработчики событий из Kafka. Получают сессию той же транзакции, в которой
отмечается processed_event — поэтому повторная доставка ничего не задвоит."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from example_service.domain.item import Item
from example_service.infra.db.repositories import SqlAlchemyItemRepository
from platform_common.kafka.events import Event

TOPICS = ["auth.events"]


async def on_user_registered(session: AsyncSession, event: Event) -> None:
    owner_id = UUID(event.payload["user_id"])
    name = event.payload.get("name", "")
    item = Item.create(owner_id, f"Welcome, {name}!", "Создано из события auth.user_registered.v1")
    await SqlAlchemyItemRepository(session).add(item)


HANDLERS = {
    "auth.user_registered.v1": on_user_registered,
}
