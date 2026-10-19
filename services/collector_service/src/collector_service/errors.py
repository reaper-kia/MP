"""Ошибки сервиса. Маппинг в gRPC-статус и публичный код — transport/grpc/errors.py."""


class CollectorError(Exception):
    pass


class InvalidRequestError(CollectorError):
    """Кривой запрос: нет периода, неизвестная площадка, start > end."""


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


class NotImplementedYetError(CollectorError):
    """Коннектор ещё не написан — честно отвечаем UNIMPLEMENTED."""
