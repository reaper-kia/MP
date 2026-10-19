"""Ошибки уровня приложения. Маппинг в gRPC-статус и публичный код — transport/grpc/errors.py.

Сообщения — по-русски, их видит пользователь. Для ошибок валидации формат «<поле>: <текст>».
"""


class SourceNotFoundError(Exception):
    pass


class SourceAlreadyExistsError(Exception):
    pass


class SearchNotFoundError(Exception):
    pass


class SearchInvalidParamsError(Exception):
    pass


class SearchNotFinishedError(Exception):
    pass


class ResultNotFoundError(Exception):
    pass


class NotImplementedYetError(Exception):
    """Сценарий ещё не написан — отвечаем UNIMPLEMENTED (gateway: 501 NOT_IMPLEMENTED)."""


class UpstreamError(Exception):
    """Ошибка соседнего сервиса (collector, ml) с его публичным кодом.

    code: UNSUPPORTED_URL, SOURCE_NOT_FOUND, SOURCE_PRIVATE, PLATFORM_UNAVAILABLE, RATE_LIMITED,
          TIMEOUT, NOT_IMPLEMENTED, ML_UNAVAILABLE, VALIDATION_ERROR, UPSTREAM_ERROR
    """

    def __init__(self, service: str, code: str, message: str) -> None:
        super().__init__(message)
        self.service = service
        self.code = code
        self.message = message
