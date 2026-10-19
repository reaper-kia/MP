class SearchDomainError(Exception):
    pass


class InvalidPeriodError(SearchDomainError):
    """Сообщение в формате «<поле>: <текст>» — gateway разложит его в details."""


class InvalidStatusTransitionError(SearchDomainError):
    """Например, finish() при незавершённых целях (B2-01)."""
