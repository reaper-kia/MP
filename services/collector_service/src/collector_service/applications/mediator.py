"""Mediator (CQRS): запрос → цепочка поведений (behaviors) → хэндлер.

Сервис только читает с площадок, поэтому все его запросы — Query. Сквозные вещи (лог и время,
кэш) — это поведения: оборачивают любой хэндлер и не повторяются в каждом из них.
Порядок поведений = порядок регистрации: первое зарегистрированное — самое внешнее.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Generic, Protocol, TypeVar, cast

TResult = TypeVar("TResult")


class Query(Generic[TResult]):  # noqa: UP046
    """Маркер: запрос на чтение, который возвращает TResult."""


# Совместимость с search_service, где тот же маркер называется Command
Command = Query


class QueryHandler[TQuery, R](Protocol):
    async def handle(self, query: TQuery) -> R: ...


# Совместимое имя
CommandHandler = QueryHandler

type Next = Callable[[], Awaitable[Any]]


class PipelineBehavior(Protocol):
    """Сквозное поведение вокруг хэндлера. Должно вызвать `call_next()` ровно один раз
    (или не вызывать — например, отдать ответ из кэша)."""

    async def __call__(self, query: Query[Any], call_next: Next) -> Any: ...


class Mediator:
    def __init__(self, behaviors: list[PipelineBehavior] | None = None) -> None:
        self._handlers: dict[type[Any], QueryHandler[Any, Any]] = {}
        self._behaviors: list[PipelineBehavior] = list(behaviors or [])

    def register[R](
        self,
        query_type: type[Query[R]],
        handler: QueryHandler[Any, R],
    ) -> None:
        self._handlers[query_type] = handler

    def add_behavior(self, behavior: PipelineBehavior) -> None:
        self._behaviors.append(behavior)

    def registered(self) -> set[type[Any]]:
        return set(self._handlers)

    async def send[R](self, query: Query[R]) -> R:
        handler = self._handlers.get(type(query))
        if handler is None:
            raise LookupError(f"No handler registered for {type(query).__name__}")

        async def call_handler() -> Any:
            return await handler.handle(query)

        call: Next = call_handler
        for behavior in reversed(self._behaviors):
            call = _bind(behavior, query, call)
        return cast(R, await call())


def _bind(behavior: PipelineBehavior, query: Query[Any], call_next: Next) -> Next:
    async def step() -> Any:
        return await behavior(query, call_next)

    return step
