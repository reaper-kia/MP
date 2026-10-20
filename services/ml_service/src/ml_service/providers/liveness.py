"""Быстро понять, что Ollama пропала (ноут уснул, туннель «завис»), не тратя бюджет RPC.

Ollama на ноуте доступна через обратный SSH-туннель. Если ноут пропал из сети, sshd на сервере
ещё до ~30 с держит порт: соединение принимается, но ответа нет — запрос висел бы весь
read-таймаут (30–40 с), а бюджет AnalyzeQuery — 15 с. Поэтому: короткий connect-таймаут у клиента
и, если от Ollama давно не было ответа, перед запросом GET /api/version с коротким таймаутом.
Пока Ollama отвечает — проверки нет (лишний запрос только после паузы).
"""

import time

import httpx


class Liveness:
    def __init__(self, client: httpx.AsyncClient, *, timeout: float, after: float) -> None:
        self._client = client
        self._timeout = timeout
        self._after = after
        self._last_ok = float("-inf")

    def ok(self) -> None:
        self._last_ok = time.monotonic()

    async def check(self) -> None:
        """httpx.HTTPError, если Ollama не ответила за timeout. after ≤ 0 — не проверяем."""
        if self._after <= 0 or time.monotonic() - self._last_ok < self._after:
            return
        response = await self._client.get("/api/version", timeout=self._timeout)
        response.raise_for_status()
        self.ok()


def ollama_timeout(read: float, connect: float) -> httpx.Timeout:
    """Подключение — быстро (ноут недоступен → сразу ошибка), ответ модели — долго."""
    return httpx.Timeout(read, connect=min(connect, read) if connect > 0 else read)
