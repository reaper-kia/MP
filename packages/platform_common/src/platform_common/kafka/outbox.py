"""Transactional outbox.

Модели в сервисе:

    class OutboxMessage(OutboxMixin, Base): ...
    class ProcessedEvent(ProcessedEventMixin, Base): ...      # если сервис ещё и consumer

В UoW: `self.outbox = OutboxWriter(session, OutboxMessage, producer="auth")`,
в хэндлере: `uow.outbox.add("auth.events", "auth.user_registered.v1", {...}, key=str(user.id))`.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from platform_common.kafka.events import Event
from platform_common.kafka.producer import EventPublisher
from platform_common.time import utcnow

logger = logging.getLogger(__name__)


class OutboxMixin:
    __tablename__ = "outbox"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(255))
    key: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class ProcessedEventMixin:
    __tablename__ = "processed_events"

    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(255))
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OutboxWriter:
    def __init__(self, session: AsyncSession, model: type[OutboxMixin], producer: str) -> None:
        self._session = session
        self._model = model
        self._producer = producer

    def add(
        self, topic: str, event_type: str, payload: dict[str, Any], *, key: str | None = None
    ) -> Event:
        event = Event(type=event_type, payload=payload, producer=self._producer)
        row = self._model()
        row.id = event.id
        row.topic = topic
        row.key = key
        row.payload = event.to_dict()
        self._session.add(row)
        return event


class OutboxRelay:
    """Фоновая задача: читает неопубликованные строки и шлёт в Kafka (at-least-once)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        model: type[OutboxMixin],
        publisher: EventPublisher,
        *,
        batch_size: int = 100,
        idle_interval: float = 0.5,
    ) -> None:
        self._session_factory = session_factory
        self._model = model
        self._publisher = publisher
        self._batch_size = batch_size
        self._idle_interval = idle_interval

    async def run(self) -> None:
        await self._publisher.start()
        logger.info("Outbox relay started")
        try:
            while True:
                sent = await self.publish_batch()
                if sent == 0:
                    await asyncio.sleep(self._idle_interval)
        finally:
            await self._publisher.stop()

    async def publish_batch(self) -> int:
        model = self._model
        async with self._session_factory() as session, session.begin():
            stmt = (
                select(model)
                .where(model.published_at.is_(None))
                .order_by(model.created_at)
                .limit(self._batch_size)
                .with_for_update(skip_locked=True)
            )
            rows = (await session.execute(stmt)).scalars().all()
            for row in rows:
                await self._publisher.publish(row.topic, row.key, row.payload)
                row.published_at = utcnow()
        if rows:
            logger.info("Outbox relay published %d event(s)", len(rows))
        return len(rows)
