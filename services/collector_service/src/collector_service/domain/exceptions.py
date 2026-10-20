"""Ошибки, которые возникают при работе с площадкой.

Ошибки уровня приложения (кривой запрос, не реализовано) — в applications/exceptions.py.
Маппинг в gRPC-статус и публичный код — transport/grpc/errors.py.
"""


class CollectorError(Exception):
    """str(exc) — текст для сотрудника: search_service показывает его в интерфейсе как есть.
    Поэтому в нём нет кодов HTTP, «rpc error» и имён переменных окружения (B1-13).

    detail — подробность для разработчика: статус, ответ площадки, что проверить. Только в лог
    (log_text), наружу не уходит.
    """

    def __init__(self, message: str = "", *, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail


class UnsupportedUrlError(CollectorError):
    """Ссылка не похожа на группу/канал поддерживаемой площадки."""


class SourceNotFoundError(CollectorError):
    pass


class SourcePrivateError(CollectorError):
    """Закрытая группа — контент недоступен."""


class PlatformUnavailableError(CollectorError):
    """Площадка не отвечает, нет ключа, анти-бот."""


class MethodUnavailableError(PlatformUnavailableError):
    """Площадка отвечает, но этот метод нашему ключу закрыт (VK 1051 — newsfeed.search для токена
    пользователя). Не «площадка лежит»: можно перейти на запасной путь."""


class RateLimitedError(CollectorError):
    pass


def log_text(exc: BaseException) -> str:
    """Текст ошибки для лога: сообщение сотруднику + подробность, если есть."""
    detail = getattr(exc, "detail", "")
    return f"{exc} [{detail}]" if detail else str(exc)
