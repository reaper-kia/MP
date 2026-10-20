"""Откуда VkApiClient берёт ключ: постоянный (сервисный ключ) или токен VK ID с автообновлением.

Сервисный ключ VK выдаёт только подтверждённому бизнес-аккаунту. Токен пользователя VK ID
(scripts/vk_token.py) получает любой аккаунт, но живёт час — поэтому VkIdToken сам обновляет его
по refresh_token до истечения и по просьбе клиента (ошибка 5). VK ID выдаёт новый refresh_token
при каждом обновлении, старый перестаёт работать — поэтому состояние пишется обратно в файл.
"""

import asyncio
import contextlib
import json
import logging
import os
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from collector_service.domain import messages
from collector_service.domain.exceptions import PlatformUnavailableError
from collector_service.infra.vk_api.transport import FormPoster, TransportError

logger = logging.getLogger(__name__)

VKID_TOKEN_URL = "https://id.vk.com/oauth2/auth"
REFRESH_MARGIN_SECONDS = 120  # обновляем заранее, чтобы запрос не упал на границе часа
REFRESH_HINT = "запустите python3 scripts/vk_token.py и перезапустите сборщик"


class TokenSource(Protocol):
    @property
    def configured(self) -> bool: ...

    @property
    def refreshable(self) -> bool: ...

    async def token(self) -> str:
        """Действующий ключ. Нет ключа — пустая строка (клиент сам скажет «не настроен»)."""
        ...

    async def refresh(self) -> str:
        """Принудительно обновить (VK ответил «ключ недействителен»)."""
        ...


class StaticToken:
    """Сервисный ключ или токен из .env: не обновляется."""

    def __init__(self, token: str) -> None:
        self._token = token.strip()

    @property
    def configured(self) -> bool:
        return bool(self._token)

    @property
    def refreshable(self) -> bool:
        return False

    async def token(self) -> str:
        return self._token

    async def refresh(self) -> str:
        return self._token


class VkIdToken:
    """Токен VK ID из файла scripts/vk_token.py: {access_token, expires_at, refresh_token,
    device_id}. Обновляется сам; файл переписывается атомарно (через временный)."""

    def __init__(
        self,
        poster: FormPoster,
        path: Path,
        client_id: str,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._poster = poster
        self._path = path
        self._client_id = client_id
        self._clock = clock
        self._lock = asyncio.Lock()
        self._state: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("VK ID: не прочитан %s (%s)", self._path, type(exc).__name__)
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def configured(self) -> bool:
        return bool(self._state.get("access_token") or self._state.get("refresh_token"))

    @property
    def refreshable(self) -> bool:
        return bool(self._state.get("refresh_token") and self._state.get("device_id"))

    def _fresh(self) -> bool:
        expires_at = self._state.get("expires_at")
        return bool(self._state.get("access_token")) and (
            isinstance(expires_at, (int, float))
            and self._clock() < expires_at - REFRESH_MARGIN_SECONDS
        )

    async def token(self) -> str:
        if self._fresh() or (self._state.get("access_token") and not self.refreshable):
            return str(self._state["access_token"])
        return await self.refresh()

    async def refresh(self) -> str:
        seen = self._state.get("access_token")
        async with self._lock:
            # файл мог обновить scripts/vk_token.py (новый вход) — его состояние главнее нашего
            disk = self._load()
            if disk.get("refresh_token") and disk != self._state:
                self._state = disk
            # пока ждали замок, токен мог обновить параллельный запрос или скрипт — хватит его
            if self._state.get("access_token") != seen and self._fresh():
                return str(self._state["access_token"])
            if not self.refreshable:
                raise PlatformUnavailableError(
                    messages.access_denied("ВКонтакте"),
                    detail=f"VK ID: токен истёк, обновить нечем — {REFRESH_HINT}",
                )
            form = {
                "grant_type": "refresh_token",
                "refresh_token": str(self._state["refresh_token"]),
                "client_id": self._client_id,
                "device_id": str(self._state["device_id"]),
                "state": secrets.token_urlsafe(16),
            }
            try:
                answer = await self._poster.post_form(VKID_TOKEN_URL, form)
            except TransportError as exc:
                raise PlatformUnavailableError(
                    messages.no_answer("ВКонтакте"),
                    detail=f"VK ID: не удалось обновить токен ({exc}) — {REFRESH_HINT}",
                ) from None
            if not isinstance(answer, dict) or "access_token" not in answer:
                raise PlatformUnavailableError(
                    messages.access_denied("ВКонтакте"),
                    detail=f"VK ID: отказ в обновлении токена — {REFRESH_HINT}",
                )
            expires_in = answer.get("expires_in")
            self._state.update(
                access_token=answer["access_token"],
                refresh_token=answer.get("refresh_token", self._state["refresh_token"]),
                expires_at=self._clock() + (expires_in if isinstance(expires_in, int) else 3600),
            )
            self._save()
            logger.info("VK ID: токен обновлён")
            return str(self._state["access_token"])

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        try:
            owner = self._path.stat()
            tmp.write_text(json.dumps(self._state), encoding="utf-8")
            tmp.chmod(0o600)
            with contextlib.suppress(OSError):
                # сборщик в контейнере — root: файл должен остаться у хозяина (scripts/vk_token.py)
                os.chown(tmp, owner.st_uid, owner.st_gid)
            os.replace(tmp, self._path)
        except OSError as exc:
            # не смертельно: этот процесс продолжит с токеном в памяти
            logger.warning("VK ID: не записан %s (%s)", self._path, type(exc).__name__)
