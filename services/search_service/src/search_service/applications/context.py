from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Контекст запроса от gateway. Авторизации в продукте нет — только request_id для логов."""

    request_id: str
