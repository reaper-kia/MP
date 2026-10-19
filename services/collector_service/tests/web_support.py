"""Подстановка страниц вместо сети для коннекторов OK / MAX / сайтов."""

from collections.abc import Mapping
from pathlib import Path

from collector_service.domain.exceptions import CollectorError
from collector_service.infra.web.fetcher import WebPage, check_response

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read(relative: str) -> str:
    return (FIXTURES / relative).read_text(encoding="utf-8")


class ScriptedWeb:
    """url → текст страницы, статус или исключение. Неизвестный url — 404."""

    def __init__(self, pages: Mapping[str, str | int | CollectorError]) -> None:
        self.pages = dict(pages)
        self.requested: list[str] = []
        self.posted: list[tuple[str, dict[str, str], dict[str, str]]] = []

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        what: str = "",
    ) -> WebPage:
        key = url + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else "")
        return self._reply(key, what)

    async def post(
        self,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        what: str = "",
    ) -> WebPage:
        self.posted.append((url, dict(data or {}), dict(headers or {})))
        return self._reply(url, what)

    def _reply(self, key: str, what: str) -> WebPage:
        self.requested.append(key)
        reply = self.pages.get(key, 404)
        if isinstance(reply, CollectorError):
            raise reply
        if isinstance(reply, int):
            return check_response(WebPage(url=key, status=reply, text=""), what or key)
        return check_response(WebPage(url=key, status=200, text=reply), what or key)
