"""HTTP GET /health — для нас, не для пользователя: какой провайдер сейчас отвечает.

ml_service — gRPC-сервис, а «ноут или Яндекс?» хочется смотреть обычным curl на сервере:
    curl -s localhost:8085/health
Без новых зависимостей: минимальный HTTP/1.0 на asyncio. Наружу порт не публикуем
(compose: 127.0.0.1:8085).
"""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

MAX_REQUEST = 8192


async def start_health_server(
    address: str, status: Callable[[], dict[str, Any]]
) -> asyncio.Server | None:
    """address «host:port»; пусто — не поднимаем. Не удалось — пишем в лог, сервис работает."""
    if not address.strip():
        return None
    host, _, port = address.rpartition(":")
    host = host.strip("[]") or "0.0.0.0"

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            line = head[:MAX_REQUEST].split(b"\r\n", 1)[0].decode("latin-1")
            method, path, *_ = (line.split(" ") + ["", ""])[:3]
            if method == "GET" and path.split("?")[0] in ("/health", "/health/"):
                code, body = "200 OK", {"status": "ok", **status()}
            else:
                code, body = "404 Not Found", {"error": "GET /health"}
            data = json.dumps(body, ensure_ascii=False, indent=2).encode()
            writer.write(
                f"HTTP/1.0 {code}\r\nContent-Type: application/json; charset=utf-8\r\n"
                f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n".encode()
                + data
            )
            await writer.drain()
        except (TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, OSError):
            pass
        finally:
            writer.close()

    try:
        server = await asyncio.start_server(handle, host, int(port), limit=MAX_REQUEST)
    except (OSError, ValueError) as e:
        logger.warning("HTTP /health не поднят на %s: %s", address, e)
        return None
    logger.info("HTTP /health on %s", address)
    return server
