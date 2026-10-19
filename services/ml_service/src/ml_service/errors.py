class MlError(Exception):
    pass


class InvalidRequestError(MlError):
    """Пустой запрос, слишком много постов, дубли id."""


class MlUnavailableError(MlError):
    """Модель недоступна и фолбэк невозможен. Обычно не бросаем — отвечаем эвристикой."""


class ProviderNotConfiguredError(MlError):
    """Провайдер выбран в настройках, но не реализован / нет ключей."""
