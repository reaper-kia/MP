"""Общее для тестов VK: заготовленные ответы вместо сети и загрузка fixtures."""

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from collector_service.infra.vk_api.transport import TransportError

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vk"

type Reply = Mapping[str, Any] | Exception | Callable[[Mapping[str, str]], Any]


def fixture(name: str) -> dict[str, Any]:
    """Файл целиком: {"_synthetic": ..., "response": ...} — ровно то, что вернул бы VK."""
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


def ok(response: Any) -> dict[str, Any]:
    return {"response": response}


def vk_error(code: int) -> dict[str, Any]:
    return {"error": {"error_code": code, "error_msg": "synthetic error"}}


class ScriptedVk:
    """Подставляется вместо сети. Ответы на метод идут по очереди; последний повторяется."""

    def __init__(self, **replies: Reply | list[Reply]) -> None:
        self.replies = {k.replace("_", "."): v for k, v in replies.items()}
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.urls: list[str] = []

    def methods(self) -> list[str]:
        return [method for method, _ in self.calls]

    def params(self, method: str) -> list[dict[str, str]]:
        return [form for name, form in self.calls if name == method]

    async def post_form(self, url: str, data: Mapping[str, str]) -> Any:
        method = url.rsplit("/", 1)[-1]
        self.urls.append(url)
        self.calls.append((method, dict(data)))
        scripted = self.replies.get(method)
        if scripted is None:
            raise AssertionError(f"Неожиданный вызов {method}")
        queue = scripted if isinstance(scripted, list) else [scripted]
        index = sum(1 for name, _ in self.calls[:-1] if name == method)
        reply = queue[min(index, len(queue) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply(data) if callable(reply) else reply


def network_down() -> TransportError:
    return TransportError("ConnectError")
