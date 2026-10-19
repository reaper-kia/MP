"""request_id входящего запроса (его присылает gateway): в логи и во все вызовы соседей (B2-12).

Хранится в ContextVar: фоновая задача пайплайна создаётся из обработчика StartSearch / RetrySearch,
поэтому наследует контекст этого запроса — передавать request_id по цепочке аргументов не нужно.
"""

from contextvars import ContextVar

import structlog

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def bind_request_id(request_id: str) -> None:
    """Запомнить request_id текущего запроса и добавить его ко всем логам этого контекста."""
    _request_id.set(request_id)
    if request_id:
        structlog.contextvars.bind_contextvars(request_id=request_id)
    else:
        structlog.contextvars.unbind_contextvars("request_id")


def current_request_id() -> str:
    return _request_id.get()
