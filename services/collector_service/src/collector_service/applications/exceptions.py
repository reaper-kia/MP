"""Ошибки уровня приложения. Ошибки площадок — в domain/exceptions.py.

Маппинг в gRPC-статус и публичный код — transport/grpc/errors.py.
"""

from collector_service.domain.exceptions import CollectorError


class InvalidRequestError(CollectorError):
    """Кривой запрос: нет периода, неизвестная площадка, start > end."""


class NotImplementedYetError(CollectorError):
    """Коннектор ещё не написан — честно отвечаем UNIMPLEMENTED."""
