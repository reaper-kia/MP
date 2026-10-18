"""Минимальный Mediator: команда/запрос → один обработчик.

@dataclass(frozen=True)
class CreateItem(Command[ItemView]):
    ctx: RequestContext
    title: str

mediator.register(CreateItem, CreateItemHandler(uow_factory))
view = await mediator.send(CreateItem(ctx, "x"))   # тип результата выводится
"""

from typing import Any, Protocol, cast


class Request[TResult]:
    """Маркер сообщения, возвращающего TResult."""


class Command[TResult](Request[TResult]):
    """Изменяет состояние."""


class Query[TResult](Request[TResult]):
    """Только читает."""


class Handler[TRequest, TResult](Protocol):
    async def handle(self, request: TRequest) -> TResult: ...


class Mediator:
    def __init__(self) -> None:
        self._handlers: dict[type[Any], Handler[Any, Any]] = {}

    def register[R](self, request_type: type[Request[R]], handler: Handler[Any, R]) -> None:
        if request_type in self._handlers:
            raise ValueError(f"Handler for {request_type.__name__} already registered")
        self._handlers[request_type] = handler

    async def send[R](self, request: Request[R]) -> R:
        handler = self._handlers.get(type(request))
        if handler is None:
            raise LookupError(f"No handler registered for {type(request).__name__}")
        return cast(R, await handler.handle(request))
