from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Контекст запроса от gateway. Авторизации в продукте нет — только request_id для логов.

    time_remaining — сколько секунд вызывающий ещё готов ждать ответ (gRPC deadline), если он
    его задал. По нему сборщик заканчивает работу раньше и отдаёт то, что успел (B1-09 п. 2).
    """

    request_id: str
    time_remaining: float | None = None
