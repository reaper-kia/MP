import asyncio
import json
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def publish(self, topic: str, key: str | None, value: dict[str, Any]) -> None: ...


class KafkaPublisher:
    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap = bootstrap_servers
        self._producer: Any = None

    async def start(self) -> None:
        from aiokafka import AIOKafkaProducer  # ленивый импорт: без Kafka модуль не нужен

        while True:
            producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap,
                value_serializer=lambda v: json.dumps(v).encode(),
                key_serializer=lambda k: k.encode() if k else None,
                enable_idempotence=True,
                acks="all",
            )
            try:
                await producer.start()
                self._producer = producer
                return
            except Exception as exc:
                logger.warning("Kafka is not ready (%s), retry in 3s", exc)
                await producer.stop()
                await asyncio.sleep(3)

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        if self._producer is None:
            raise RuntimeError("KafkaPublisher is not started")
        await self._producer.send_and_wait(topic, value=value, key=key)
