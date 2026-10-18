"""Все gRPC-клиенты Gateway. Один канал на сервис, создаются лениво при старте."""

from typing import Any

from grpc import aio

from contracts.auth.v1 import auth_pb2_grpc
from contracts.example.v1 import example_pb2_grpc

# >>> grpc imports (new_service.py вставляет строки выше)
from gateway.config import Settings
from platform_common.grpc.client import create_channel


class GrpcClients:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._channels: dict[str, aio.Channel] = {}
        self.auth: Any = auth_pb2_grpc.AuthServiceStub(
            self._channel("auth", settings.auth_grpc_target)
        )
        self.example: Any = example_pb2_grpc.ExampleServiceStub(
            self._channel("example", settings.example_grpc_target)
        )
        # >>> grpc clients (new_service.py вставляет строки выше)

    def _channel(self, name: str, target: str) -> aio.Channel:
        channel = create_channel(target, timeout=self._settings.grpc_timeout)
        self._channels[name] = channel
        return channel

    def names(self) -> list[str]:
        return list(self._channels)

    def channel(self, name: str) -> aio.Channel:
        return self._channels[name]

    async def close(self) -> None:
        for channel in self._channels.values():
            await channel.close()
