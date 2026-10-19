"""Ошибки, которые возникают при работе с площадкой.

Ошибки уровня приложения (кривой запрос, не реализовано) — в applications/exceptions.py.
Маппинг в gRPC-статус и публичный код — transport/grpc/errors.py.
"""


class CollectorError(Exception):
    pass


class UnsupportedUrlError(CollectorError):
    """Ссылка не похожа на группу/канал поддерживаемой площадки."""


class SourceNotFoundError(CollectorError):
    pass


class SourcePrivateError(CollectorError):
    """Закрытая группа — контент недоступен."""


class PlatformUnavailableError(CollectorError):
    """Площадка не отвечает, нет ключа, анти-бот."""


class RateLimitedError(CollectorError):
    pass
