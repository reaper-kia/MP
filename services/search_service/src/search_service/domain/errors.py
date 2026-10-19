class DomainError(Exception):
    """Нарушение инварианта домена."""


class NotFoundError(DomainError):
    pass


class SourceAlreadyExists(DomainError):
    pass


class SearchInvalidParams(DomainError):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


class SearchNotFinished(DomainError):
    pass


class CollectorError(DomainError):
    """Ошибка внешнего коллектора с кодом для mark_failed."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)
