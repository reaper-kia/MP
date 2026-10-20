from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Контекст запроса от gateway. Авторизации в продукте нет (по ТЗ).

    request_id — для логов; actor — анонимный id браузера (заголовок X-Client-Id, gateway кладёт его
    в actor_user_id): история поисков у каждого своя. Пусто — история пустая.
    """

    request_id: str
    actor: str = ""
