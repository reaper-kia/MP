"""Ошибки домена (B2) → ошибки приложения, которые transport/grpc/errors.py знает в лицо.

Сценарии B2 бросают DomainError и наследников с кодом в тексте (NotFoundError("SEARCH_NOT_FOUND")).
Хэндлеры медиатора оборачивают вызовы в `with domain_errors():`.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from search_service.applications.exceptions import (
    ResultNotFoundError,
    SearchInvalidParamsError,
    SearchNotFinishedError,
    SearchNotFoundError,
    SourceAlreadyExistsError,
    SourceNotFoundError,
    UpstreamError,
)
from search_service.domain.errors import (
    CollectorError,
    DomainError,
    NotFoundError,
    SearchInvalidParams,
    SearchNotFinished,
    SourceAlreadyExists,
)
from search_service.domain.exceptions import InvalidStatusTransitionError

SOURCE_PRIVATE_MESSAGE = "Группа закрыта — публикации недоступны"


def _not_found(e: NotFoundError) -> Exception:
    code = str(e).split(":", 1)[0].strip()
    if code == "SOURCE_NOT_FOUND":
        return SourceNotFoundError("Источник не найден")
    if code == "RESULT_NOT_FOUND":
        return ResultNotFoundError("Публикация не найдена в подборке")
    if code == "TARGET_NOT_FOUND":
        return SearchInvalidParamsError("target_ids: цель не найдена в этом поиске")
    return SearchNotFoundError("Поиск не найден")


@contextmanager
def domain_errors() -> Iterator[None]:
    try:
        yield
    except SearchInvalidParams as e:
        raise SearchInvalidParamsError(str(e)) from e  # «<поле>: <текст>»
    except SearchNotFinished as e:
        raise SearchNotFinishedError(str(e) or "Поиск ещё выполняется") from e
    except SourceAlreadyExists as e:
        raise SourceAlreadyExistsError("Источник уже есть в каталоге") from e
    except NotFoundError as e:
        raise _not_found(e) from e
    except CollectorError as e:  # стаб коллектора
        raise UpstreamError("collector", e.code, str(e)) from e
    except DomainError as e:
        if str(e) == "SOURCE_PRIVATE":
            raise UpstreamError("collector", "SOURCE_PRIVATE", SOURCE_PRIVATE_MESSAGE) from e
        raise InvalidStatusTransitionError(str(e)) from e
