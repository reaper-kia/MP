"""Интеграция с настоящим Postgres: outbox relay + идемпотентный consumer.
Пропускается, если Postgres недоступен (поднять: make infra)."""

import asyncio
import socket
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from example_service.config import Settings
from example_service.infra.db.models import ItemModel, OutboxMessage, ProcessedEvent
from example_service.main import MIGRATIONS_DIR
from example_service.transport.kafka.handlers import HANDLERS
from platform_common.db.engine import create_engine, create_session_factory, ensure_database
from platform_common.db.migrations import upgrade_head
from platform_common.kafka.consumer import EventProcessor
from platform_common.kafka.events import Event
from platform_common.kafka.outbox import OutboxRelay, OutboxWriter


def _pg_available(settings: Settings) -> bool:
    try:
        with socket.create_connection((settings.postgres_host, settings.postgres_port), timeout=1):
            return True
    except OSError:
        return False


SETTINGS = Settings(database_name="example_test")
pytestmark = pytest.mark.skipif(not _pg_available(SETTINGS), reason="Postgres is not running")


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    await ensure_database(SETTINGS.database_url)
    # alembic env сам делает asyncio.run → из работающего loop запускаем в потоке
    await asyncio.to_thread(upgrade_head, MIGRATIONS_DIR, SETTINGS.database_url)
    engine = create_engine(SETTINGS.database_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE items, outbox, processed_events"))
    yield create_session_factory(engine)
    await engine.dispose()


class MemoryPublisher:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str | None, dict[str, Any]]] = []

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def publish(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        self.sent.append((topic, key, value))


async def test_outbox_relay_publishes_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as s, s.begin():
        OutboxWriter(s, OutboxMessage, "test").add("t", "x.happened.v1", {"a": 1}, key="k")
    publisher = MemoryPublisher()
    relay = OutboxRelay(session_factory, OutboxMessage, publisher)
    assert await relay.publish_batch() == 1
    assert await relay.publish_batch() == 0
    assert publisher.sent[0][2]["type"] == "x.happened.v1"


async def test_consumer_is_idempotent(session_factory: async_sessionmaker[AsyncSession]) -> None:
    processor = EventProcessor(HANDLERS, session_factory, ProcessedEvent)
    event = Event(
        type="auth.user_registered.v1",
        payload={"user_id": str(uuid4()), "email": "a@b.co", "name": "A"},
        producer="auth",
    ).to_dict()
    assert await processor.process(event) is True
    assert await processor.process(event) is False  # повторная доставка
    async with session_factory() as s:
        assert await s.scalar(select(func.count()).select_from(ItemModel)) == 1
