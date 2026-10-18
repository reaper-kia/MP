# Рецепты

## 1. Новый сервис

```bash
make new-service name=orders entity=Order      # порт выберется сам (50053, 50054, ...)
```

Создаст `contracts/orders/v1/orders.proto`, `services/orders/` (Create/Get/List готовы, миграция, тест),
`gateway/routers/orders.py` + `schemas/orders.py`, пропишет сервис в compose, gateway и mypy.
Сразу работает: `make up` → `POST /api/v1/orders`.

Дальше переделываешь под ТЗ: proto → домен → обработчики (рецепт 2).
Удалить образец `example`, когда он мешает: папки `services/example`, `contracts/example`,
роутер `items.py`/схему, строки в `gateway/{config,clients,main}.py`, блок в `compose.yaml`, `mypy_path`.

## 2. Новый RPC (пример: отменить заказ)

1. **proto** — `contracts/orders/v1/orders.proto`:
   ```proto
   rpc CancelOrder(CancelOrderRequest) returns (CancelOrderResponse);

   message CancelOrderRequest {
     contracts.common.v1.RequestContext context = 1;
     string order_id = 2;
     string reason = 3;
   }
   message CancelOrderResponse { Order order = 1; }
   ```
   `make proto`
2. **домен** — правило и ошибка в `domain/order.py`:
   ```python
   class OrderAlreadyShipped(ConflictError):
       code = "ORDER_ALREADY_SHIPPED"


   @dataclass
   class Order:
       ...

       def cancel(self, reason: str) -> None:
           if self.status is OrderStatus.SHIPPED:
               raise OrderAlreadyShipped()
           self.status = OrderStatus.CANCELLED
   ```
3. **команда + обработчик** — `application/commands.py`:
   ```python
   @dataclass(frozen=True, slots=True)
   class CancelOrder(Command[Order]):
       ctx: RequestContext
       order_id: UUID
       reason: str


   class CancelOrderHandler:
       def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
           self._uow_factory = uow_factory

       async def handle(self, cmd: CancelOrder) -> Order:
           async with self._uow_factory() as uow:
               order = await uow.orders.get(cmd.order_id)
               if order is None:
                   raise OrderNotFoundError()
               cmd.ctx.require_owner_or_admin(order.owner_id)
               order.cancel(cmd.reason)
               await uow.orders.update(order)  # добавь метод в порт и репозиторий
               await uow.commit()
           return order
   ```
4. **регистрация** — `container.py`: `mediator.register(CancelOrder, CancelOrderHandler(uow_factory))`
5. **servicer** — `transport/grpc/servicer.py`:
   ```python
   @rpc
   async def CancelOrder(
       self, request: pb.CancelOrderRequest, context: ServicerContext
   ) -> pb.CancelOrderResponse:
       order = await self._m.send(
           CancelOrder(
               RequestContext.from_proto(request.context),
               parse_uuid(request.order_id, "order_id"),
               request.reason,
           )
       )
       return pb.CancelOrderResponse(order=order_to_pb(order))
   ```
6. **gateway** — `routers/orders.py`:
   ```python
   @router.post("/{order_id}/cancel")
   async def cancel_order(order_id: UUID, body: CancelIn, ctx: AuthCtx, clients: Clients) -> OrderOut:
       resp = await clients.orders.CancelOrder(
           pb.CancelOrderRequest(context=ctx, order_id=str(order_id), reason=body.reason)
       )
       return OrderOut.from_pb(resp.order)
   ```
7. **тест** use case'а на фейках (`services/orders/tests`) → `make check`.

## 3. Поменял модели → миграция

```bash
make infra                                  # Postgres должен быть запущен
make migration s=orders m="add status"      # autogenerate в src/orders_service/migrations/versions
```

Проверь сгенерированный файл глазами. Применяется автоматически при старте сервиса (`<svc> run`),
вручную — `make run s=orders cmd=migrate`.

## 4. Вызвать соседний сервис

Образец — `services/example/src/example_service/infra/auth_client.py`.

1. В `config.py`: `auth_grpc_target: str = "localhost:50051"`; в `compose.yaml` у сервиса: `AUTH_GRPC_TARGET: auth:50051`.
2. Порт в `application/ports.py` (Protocol), адаптер в `infra/`:
   ```python
   class GrpcUserDirectory:
       def __init__(self, channel: aio.Channel) -> None:
           self._stub = auth_pb2_grpc.AuthServiceStub(channel)

       async def get_name(self, ctx: RequestContext, user_id: UUID) -> str | None:
           try:
               resp = await self._stub.GetUser(
                   auth_pb2.GetUserRequest(context=ctx.to_proto(), user_id=str(user_id))
               )
           except aio.AioRpcError as exc:
               raise app_error_from_rpc(
                   exc
               )  # пробросить как есть (код сохранится) — или деградировать
           return resp.user.name
   ```
3. В `container.py`: `channel = create_channel(settings.auth_grpc_target, timeout=settings.grpc_client_timeout)`,
   положить в `Container.channels` (закроется при остановке).

Правило: межсервисные вызовы — **вне** открытой транзакции UoW.

## 5. События через Kafka

Публикация (в обработчике команды, в той же транзакции):
```python
uow.outbox.add(
    "orders.events", "orders.order_created.v1", {"order_id": str(order.id)}, key=str(order.id)
)
await uow.commit()
```
Подписка (в сервисе-потребителе):
1. модель `class ProcessedEvent(ProcessedEventMixin, Base)` + миграция;
2. `transport/kafka/handlers.py`: `async def on_order_created(session, event): ...`, `HANDLERS = {"orders.order_created.v1": on_order_created}`, `TOPICS = ["orders.events"]`;
3. в `container.py` — `KafkaEventConsumer(...)` в `background` (см. example).

Запуск: `make up-kafka` (или `KAFKA_ENABLED=true` в `.env` + `make infra-kafka` для локального запуска).
Без Kafka всё работает: события копятся в `outbox` и уйдут, когда включишь.
Не забудь строку в `docs/events.md`.

## 6. WebSocket-команда

`services/gateway/src/gateway/ws/handlers.py`:
```python
@ws_handler("room.bet")
async def place_bet(
    conn: Connection, payload: dict[str, Any], app: FastAPI, request_id: str
) -> Any:
    resp = await app.state.clients.casino.PlaceBet(
        casino_pb2.PlaceBetRequest(
            context=conn_context(conn, request_id), amount=int(payload["amount"])
        )
    )
    await app.state.ws.broadcast(f"room:{payload['room_id']}", "bet.placed", {...})
    return {"bet_id": resp.bet.id}  # клиенту уйдёт "room.bet.ok"
```
Ошибки gRPC/AppError сами превращаются в `{"type": "error", ...}`.

## 7. Фронт

- Типы и вызовы API — `frontend/src/api/index.ts` (по образцу `items`).
- `request()` сам добавляет Bearer, на 401 делает refresh и повторяет запрос.
- WebSocket — `connectWs(getAccessToken, onMessage)` из `src/api/ws.ts`, возвращает `{send, close}`.
- Dev: `make front-dev` (Vite проксирует `/api` и `/ws` на `localhost:8000`).

## 8. Деплой

```bash
make server-setup HOST=1.2.3.4 SSH_USER=ubuntu    # один раз
make deploy HOST=1.2.3.4 SSH_USER=ubuntu          # каждый раз
make smoke URL=http://1.2.3.4
```
Подробности — `infra/ansible/README.md`.

## Если что-то не так

| Симптом | Что делать |
|---|---|
| `port is already allocated` на 80/8000/5432/6379 | В `.env`: `HTTP_PORT=8080`, `GATEWAY_PORT=8001`, `POSTGRES_PORT=5433`, `REDIS_PORT=6380` (+ `REDIS_URL=redis://localhost:6380/0` для `make run`) |
| Docker Hub не качается | На сервере зеркала ставит `server-setup`; локально — `"registry-mirrors": ["https://mirror.gcr.io"]` в `/etc/docker/daemon.json` |
| `503 SERVICE_UNAVAILABLE` | сервис лежит: `make ps`, `make logs s=<svc>`; `/health/ready` покажет кого нет |
| `502 UPSTREAM_ERROR` | необработанное исключение в сервисе — traceback в его логах (ищи по request_id) |
| Ручка не видит новый RPC | забыл `make proto`; в Docker — `make up` (пересоберёт) |
| `Can't locate revision` / таблицы нет | `make migration ...` не запускали или миграция не применена: `make run s=<svc> cmd=migrate` |
| refresh не работает на сервере | HTTP без TLS → `cookie_secure: false` (по умолчанию так) |
| Где request_id? | заголовок `X-Request-ID` ответа и поле `error.request_id`; `make logs | grep <id>` покажет путь по всем сервисам |
