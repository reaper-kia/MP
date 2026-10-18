"""Идемпотентный consumer: event_id пишется в processed_events в той же транзакции,
что и изменения обработчика. Дубликат (at-least-once) просто пропускается.

    handlers = {"auth.user_registered.v1": on_user_registered}
    consumer = KafkaEventConsumer(
        bootstrap_servers=..., group_id="example", topics=["auth.events"],
        handlers=handlers, session_factory=sf, processed_model=ProcessedEvent,
    )
    # передать consumer.run в background у run_grpc_server
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_common.context import request_id_var
from platform_common.kafka.events import Event
from platform_common.kafka.outbox import ProcessedEventMixin

logger = logging.getLogger(__name__)

type EventHandler = Callable[[AsyncSession, Event], Awaitable[None]]


class EventProcessor:
    """Обработка одного события — отдельно от Kafka, чтобы тестировать без брокера."""

    def __init__(
        self,
        handlers: Mapping[str, EventHandler],
        session_factory: async_sessionmaker[AsyncSession],
        processed_model: type[ProcessedEventMixin],
    ) -> None:
        self._handlers = handlers
        self._session_factory = session_factory
        self._processed = processed_model

    async def process(self, raw: dict[str, Any]) -> bool:
        """True — обработано сейчас, False — дубликат или нет обработчика."""
        event = Event.from_dict(raw)
        handler = self._handlers.get(event.type)
        if handler is None:
            return False
        request_id_var.set(f"event:{event.id}")
        async with self._session_factory() as session, session.begin():
            stmt = (
                pg_insert(self._processed)
                .values(event_id=event.id, event_type=event.type)
                .on_conflict_do_nothing()
                .returning(self._processed.event_id)
            )
            if (await session.execute(stmt)).scalar_one_or_none() is None:
                logger.info("Duplicate event %s skipped", event.id)
                return False
            await handler(session, event)
        logger.info("Processed %s", event.type)
        return True


class KafkaEventConsumer:
    def __init__(
        self,
        *,
        bootstrap_servers: str,
        group_id: str,
        topics: Sequence[str],
        handlers: Mapping[str, EventHandler],
        session_factory: async_sessionmaker[AsyncSession],
        processed_model: type[ProcessedEventMixin],
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._group_id = group_id
        self._topics = list(topics)
        self._processor = EventProcessor(handlers, session_factory, processed_model)

    async def run(self) -> None:
        from aiokafka import AIOKafkaConsumer  # ленивый импорт

        while True:
            consumer = AIOKafkaConsumer(
                *self._topics,
                bootstrap_servers=self._bootstrap,
                group_id=self._group_id,
                enable_auto_commit=False,
                auto_offset_reset="earliest",
                value_deserializer=lambda v: json.loads(v.decode()),
            )
            try:
                await consumer.start()
                break
            except Exception as exc:
                logger.warning("Kafka is not ready (%s), retry in 3s", exc)
                await consumer.stop()
                await asyncio.sleep(3)

        logger.info("Consumer %s subscribed to %s", self._group_id, self._topics)
        try:
            async for message in consumer:
                # Ошибка обработчика → исключение → offset не закоммичен →
                # supervisor перезапустит consumer и событие придёт снова.
                await self._processor.process(message.value)
                await consumer.commit()
        finally:
            await consumer.stop()
