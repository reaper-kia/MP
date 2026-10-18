# MP — микросервисы на gRPC за единым Gateway

Каркас для хакатона: транспорт, авторизация, ошибки, миграции, Docker и деплой уже сделаны.
На месте остаётся описать контракты (`.proto`) и написать бизнес-логику.

```
Браузер ──HTTP/WS──▶ nginx (frontend :80) ──▶ Gateway (FastAPI :8000) ──gRPC──▶ auth    :50051
                                                 │ JWT → RequestContext            example :50052
                                                 │ ошибки gRPC → HTTP              <ваши>  :50053+
                                                 │ WebSocket, rate limit (Redis)       │
                                                                                       ├─ Postgres (своя БД у каждого)
                                                                                       └─ outbox → Kafka (по желанию)
```

**Работает из коробки:** регистрация, логин, refresh-токен в HttpOnly cookie, logout; образец CRUD-сервиса;
вызов одного сервиса из другого; единый формат ошибок; сквозной `request_id` в логах всех сервисов;
WebSocket с группами и push-событиями; outbox и идемпотентный consumer (Kafka включается флагом);
автосоздание БД и миграции при старте; генератор новых сервисов; тесты; CI; деплой на сервер по IP.

---

## Содержание

1. [Установка](#1-установка)
2. [Первый запуск](#2-первый-запуск)
3. [Два режима работы](#3-два-режима-работы)
4. [Как устроен запрос](#4-как-устроен-запрос)
5. [Гайд: от ТЗ до работающей фичи](#5-гайд-от-тз-до-работающей-фичи)
6. [Работа в команде](#6-работа-в-команде)
7. [Структура проекта](#7-структура-проекта)
8. [Все команды](#8-все-команды)
9. [Конфигурация (.env)](#9-конфигурация-env)
10. [Ошибки, права, пагинация](#10-ошибки-права-пагинация)
11. [WebSocket](#11-websocket)
12. [Kafka и события](#12-kafka-и-события)
13. [Тесты и CI](#13-тесты-и-ci)
14. [Деплой на сервер](#14-деплой-на-сервер)
15. [Отладка](#15-отладка)
16. [Как убрать образец example](#16-как-убрать-образец-example)
17. [Залить в свой GitHub](#17-залить-в-свой-github)

Дополнительно: [docs/recipes.md](docs/recipes.md) — короткие рецепты и таблица проблем,
[docs/conventions.md](docs/conventions.md) — все соглашения в одном месте,
[docs/events.md](docs/events.md) — реестр событий.

---

## 1. Установка

Нужно: **Python 3.13**, **[uv](https://docs.astral.sh/uv/)**, **Docker + compose + buildx**, **Node 22** (для фронта
локально), **Ansible + rsync** (только для деплоя).

Arch:

```bash
sudo pacman -S python uv docker docker-compose docker-buildx nodejs npm ansible rsync
sudo systemctl enable --now docker
sudo usermod -aG docker $USER      # перелогиниться
```

Ubuntu:

```bash
sudo apt install -y python3 docker.io docker-compose-v2 docker-buildx nodejs npm ansible rsync make
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo usermod -aG docker $USER
```

Проверка: `uv --version && docker compose version && node --version`.

## 2. Первый запуск

```bash
make install     # создаёт .env из .env.example и ставит все Python-пакеты (появится uv.lock — закоммить его)
make up          # собирает и поднимает всё в Docker
make smoke       # сквозная проверка: register → login → items → refresh → logout
```

После `make up`:

| Что | Адрес |
|---|---|
| Фронт | http://localhost |
| Swagger (все HTTP-ручки) | http://localhost:8000/docs |
| Готовность всех сервисов | http://localhost:8000/health/ready |

В Swagger: `POST /api/v1/auth/register` → скопируй `access_token` → кнопка **Authorize** → дальше любые ручки.
Админом становится email из `ADMIN_EMAILS` в `.env` (по умолчанию `admin@example.com`).

Остановить — `make down` (данные остаются), снести вместе с данными — `make reset`.

## 3. Два режима работы

**Всё в Docker** (`make up`) — для демо, проверки перед деплоем и для фронтендера, которому нужен готовый бэк.
После правок кода — снова `make up` (пересоберёт только изменившееся).

**Локальная разработка** — быстрее: сервисы перезапускаются за секунду, видны логи, работает отладчик.

```bash
make infra              # только Postgres и Redis в Docker
make run s=auth         # терминал 1
make run s=example      # терминал 2
make run s=gateway      # терминал 3  → http://localhost:8000/docs
make front-dev          # терминал 4  → http://localhost:5173 (hot reload, /api проксируется на :8000)
```

Сервис при старте сам создаёт свою БД и применяет миграции. Если в Docker уже запущен тот же сервис, его порт
занят — останови контейнер: `docker compose stop auth`.

В VS Code/PyCharm интерпретатор — `.venv/bin/python` в корне. Запуск под отладчиком: модуль
`auth_service.main` с аргументом `serve`, рабочая папка `services/auth`.

## 4. Как устроен запрос

На примере `GET /api/v1/items/{id}`:

1. **nginx** (`frontend/nginx.conf`) отдаёт статику, а `/api`, `/ws`, `/docs` проксирует в gateway.
2. **Gateway** (`services/gateway`):
   - `RequestIdMiddleware` берёт `X-Request-ID` от клиента или генерирует его;
   - зависимость `AuthCtx` проверяет JWT и собирает `RequestContext{request_id, actor_user_id, actor_role}`;
   - роутер `routers/items.py` превращает HTTP-запрос в proto-сообщение и вызывает `clients.example.GetItem(...)`.
3. **gRPC-канал** (`platform_common/grpc/client.py`) добавляет таймаут (5 с) и `x-request-id`.
4. **Сервис example**:
   - servicer (`transport/grpc/servicer.py`) с декоратором `@rpc` превращает proto в команду `GetItem(ctx, id)`;
   - `mediator.send(...)` находит обработчик в `application/queries/items.py`;
   - обработчик через Unit of Work и репозиторий достаёт сущность из БД, проверяет права
     (`ctx.require_owner_or_admin`) и вызывает **auth** по gRPC за именем владельца.
5. Ответ идёт обратно тем же путём. Если где-то брошена ошибка, например `ItemNotFoundError`:
   - `@rpc` превращает её в gRPC `NOT_FOUND` и кладёт `code=ITEM_NOT_FOUND` в metadata;
   - gateway превращает это в HTTP 404 `{"error": {"code": "ITEM_NOT_FOUND", ...}}`.

**Ни в роутерах, ни в servicer'ах нет try/except** — ошибки маппятся централизованно.

Слои внутри любого сервиса:

| Слой | Папка | Что там | Что НЕ должно быть |
|---|---|---|---|
| Домен | `domain/` | dataclass-сущности, правила, доменные ошибки | БД, gRPC, HTTP |
| Приложение | `application/` | команды/запросы + обработчики, порты (`Protocol`) | SQLAlchemy, proto |
| Инфраструктура | `infra/` | модели SQLAlchemy, репозитории, UoW, клиенты соседних сервисов | бизнес-правила |
| Транспорт | `transport/` | gRPC servicer, мапперы proto ⇄ DTO, обработчики Kafka | бизнес-правила |
| Сборка | `container.py` | связывает реализации с портами, регистрирует обработчики | — |

## 5. Гайд: от ТЗ до работающей фичи

Сквозной пример: в ТЗ «пользователь бронирует слот, может отменить бронь, нельзя забронировать занятый слот».

### Шаг 1. Разбор ТЗ (вся команда, 30–60 минут)

- Выпишите **сценарии** глаголами: «забронировать слот», «отменить бронь», «посмотреть мои брони».
- Разложите данные по **владельцам**. Один сервис = одна зона ответственности и своя БД. На хакатоне
  обычно хватает 2–4 сервисов, и auth уже есть.
- Для каждого сценария решите: **кто вызывает кого** (gRPC, синхронно, нужен ответ) и **что может случиться
  потом** (событие в Kafka, асинхронно).
- Договоритесь об **HTTP API для фронта** — по Swagger или прямо в `docs/`. Фронтендер начинает сразу.

### Шаг 2. Создать сервис (1 минута)

```bash
make new-service name=booking entity=Slot
```

Появится:

```
contracts/booking/v1/booking.proto                 ← контракт
services/booking/                                  ← сервис: Create/Get/List уже работают, есть миграция и тест
services/gateway/src/gateway/routers/booking.py    ← HTTP-ручки /api/v1/booking
services/gateway/src/gateway/schemas/booking.py    ← Pydantic-схемы
```

Плюс сервис прописан в `compose.yaml`, в gateway (`config.py`, `clients.py`, `main.py`) и в `mypy_path`.
Порт берётся следующий свободный (50053, 50054…), можно задать: `port=50060`.

Проверка: `make up` → в Swagger появились `/api/v1/booking`.

### Шаг 3. Контракт (`contracts/booking/v1/booking.proto`)

Описываешь RPC под сценарии. Правила: первое поле запроса — `RequestContext context = 1`; запрос и ответ
называются `<Rpc>Request` / `<Rpc>Response`; у enum нулевое значение `*_UNSPECIFIED`.

```proto
service BookingService {
  rpc CreateSlot(CreateSlotRequest) returns (CreateSlotResponse);
  rpc GetSlot(GetSlotRequest) returns (GetSlotResponse);
  rpc ListSlots(ListSlotsRequest) returns (ListSlotsResponse);
  rpc BookSlot(BookSlotRequest) returns (BookSlotResponse);       // новое
}

message BookSlotRequest {
  contracts.common.v1.RequestContext context = 1;
  string slot_id = 2;
}
message BookSlotResponse { Slot slot = 1; }
```

```bash
make proto      # генерирует Python в packages/contracts (руками его не трогаем)
```

### Шаг 4. Домен (`services/booking/src/booking_service/domain/slot.py`)

Правила предметной области и ошибки с публичным кодом. Никакого SQL и gRPC.

```python
class SlotAlreadyBookedError(ConflictError):          # → HTTP 409
    code = "SLOT_ALREADY_BOOKED"


@dataclass
class Slot:
    id: UUID
    owner_id: UUID
    title: str
    created_at: datetime
    booked_by: UUID | None = None

    def book(self, user_id: UUID) -> None:
        if self.booked_by is not None:
            raise SlotAlreadyBookedError()
        self.booked_by = user_id
```

Базовые классы ошибок: `ValidationError` 422, `UnauthenticatedError` 401, `PermissionDeniedError` 403,
`NotFoundError` 404, `AlreadyExistsError` 409, `ConflictError` 409, `RateLimitedError` 429.

### Шаг 5. Команда и обработчик (`application/commands.py`)

```python
@dataclass(frozen=True, slots=True)
class BookSlot(Command[Slot]):
    ctx: RequestContext
    slot_id: UUID


class BookSlotHandler:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, cmd: BookSlot) -> Slot:
        user_id = cmd.ctx.require_user()                 # 401, если не залогинен
        async with self._uow_factory() as uow:           # одна транзакция
            slot = await uow.slots.get(cmd.slot_id)
            if slot is None:
                raise SlotNotFoundError()
            slot.book(user_id)                           # бизнес-правило — в домене
            await uow.slots.update(slot)
            await uow.commit()                           # без commit всё откатится
        return slot
```

Если репозиторию нужен новый метод (`update`), добавь его в порт `application/ports.py` и в реализацию
`infra/db/repositories.py`.

Регистрация — одна строка в `container.py`:

```python
mediator.register(BookSlot, BookSlotHandler(uow_factory))
```

### Шаг 6. Модель и миграция

Добавляешь колонку в `infra/db/models.py` (`booked_by: Mapped[uuid.UUID | None]`), мапишь её в
`repositories.py`, затем:

```bash
make infra                                    # если Postgres ещё не запущен
make migration s=booking m="slot booked_by"   # autogenerate → src/booking_service/migrations/versions/
```

Посмотри на сгенерированный файл глазами. Применится сам при следующем старте сервиса.

### Шаг 7. gRPC servicer (`transport/grpc/servicer.py`)

```python
@rpc
async def BookSlot(self, request: pb.BookSlotRequest, context: ServicerContext) -> pb.BookSlotResponse:
    slot = await self._m.send(
        BookSlot(RequestContext.from_proto(request.context), parse_uuid(request.slot_id, "slot_id"))
    )
    return pb.BookSlotResponse(slot=slot_to_pb(slot))
```

### Шаг 8. HTTP-ручка в gateway (`services/gateway/src/gateway/routers/booking.py`)

```python
@router.post("/{slot_id}/book")
async def book_slot(slot_id: UUID, ctx: AuthCtx, clients: Clients) -> SlotOut:
    resp = await clients.booking.BookSlot(pb.BookSlotRequest(context=ctx, slot_id=str(slot_id)))
    return SlotOut.from_pb(resp.slot)
```

`AuthCtx` — нужен логин, `AnonCtx` — можно без него. Если нужен push в реальном времени:
`await request.app.state.ws.broadcast("slots", "slot.booked", {...})`.

### Шаг 9. Тест

`services/booking/tests/test_slot.py` уже содержит фейковые UoW и репозиторий — добавь сценарий:

```python
async def test_cannot_book_twice() -> None:
    ...
    await mediator.send(BookSlot(ctx(alice), slot.id))
    with pytest.raises(SlotAlreadyBookedError):
        await mediator.send(BookSlot(ctx(bob), slot.id))
```

```bash
make check      # ruff + mypy --strict + pytest по всем сервисам
```

### Шаг 10. Фронт

В `frontend/src/api/index.ts` по образцу `items` добавляешь типы и вызовы:

```ts
export const slots = {
  list: () => request<Page<Slot>>("GET", "/booking"),
  book: (id: string) => request<Slot>("POST", `/booking/${id}/book`),
};
```

`request()` сам подставляет токен, на 401 обновляет его через refresh-cookie и повторяет запрос,
ошибку отдаёт как `ApiError` с полем `code`. Экран — по образцу `src/pages/ItemsPage.tsx`.

### Шаг 11. Проверка и выкатка

```bash
make up && make smoke                          # локально, всё в Docker
make deploy HOST=<ip> SSH_USER=<user>          # на сервер (первый раз — make server-setup)
make smoke URL=http://<ip>
```

### Если нужен вызов соседнего сервиса

Например, booking проверяет пользователя в auth. Образец — `services/example/src/example_service/infra/auth_client.py`:

1. `config.py` сервиса: `auth_grpc_target: str = "localhost:50051"`; в `compose.yaml` у сервиса: `AUTH_GRPC_TARGET: auth:50051`.
2. Порт в `application/ports.py` (Protocol) и адаптер в `infra/`, который вызывает stub с `ctx.to_proto()`.
3. В `container.py`: `create_channel(settings.auth_grpc_target, timeout=settings.grpc_client_timeout)`,
   канал положить в `Container.channels`.
4. Ошибку соседа либо пробрасываешь (`raise app_error_from_rpc(exc)` — код сохранится до фронта),
   либо деградируешь, как example (возвращает item без имени владельца).

Межсервисные вызовы делай **вне** открытой транзакции UoW.

## 6. Работа в команде

| Кто | Где работает | Что ещё |
|---|---|---|
| Тимлид / DevOps | `platform_common`, `compose.yaml`, `infra/`, CI, `make new-service` | раздаёт сервисы, мержит контракты |
| Бэкенд 1, 2 | `services/<свой>/`, свои ручки в `gateway/routers/` | proto — через ревью |
| Фронтенд | `frontend/` | работает по Swagger поднятого `make up` |
| Дизайн / презентация | — | демо-стенд: `make up`, затем регистрируетесь во фронте |

Правила, которые экономят время:

- **Контракт — точка синхронизации.** Сначала PR с `.proto` (+ `make proto`), потом реализация. Фронту
  сразу можно дать HTTP-схему, даже если сервис ещё отвечает заглушкой.
- `make new-service` запускает один человек и сразу пушит: генератор правит общие файлы (`compose.yaml`,
  gateway), параллельный запуск даст конфликты.
- Сгенерированный код (`packages/contracts/src`) коммитится. CI проверит, что он соответствует `.proto`.
- Перед пушем — `make fmt && make check`.
- Ветки короткие, мерж часто: на хакатоне долгие ветки — главный источник боли.

## 7. Структура проекта

```
contracts/<svc>/v1/*.proto        ← контракты внутренних API (пишем руками)
packages/
  contracts/                      ← сгенерированный Python из proto (make proto)
  platform_common/                ← общий фундамент, бизнес-логики нет:
    errors.py                       иерархия ошибок с публичными кодами
    context.py                      RequestContext + проверки прав
    mediator.py                     Command / Query / Mediator
    pagination.py                   курсорная пагинация
    grpc/server.py                  запуск сервера: health, reflection, graceful shutdown, фоновые задачи
    grpc/client.py                  каналы: таймаут, x-request-id
    grpc/errors.py                  @rpc: AppError → gRPC status; обратный разбор для клиентов
    db/                             engine, UoW, ensure_database, миграции без alembic.ini
    kafka/                          Event, outbox writer/relay, idempotent consumer
    security/jwt.py                 выпуск и проверка access-токенов
    cli.py                          общий CLI сервиса: run | serve | migrate | makemigrations
services/
  gateway/                        ← HTTP + WebSocket, единственный вход снаружи
    routers/ schemas/ ws/           ручки, Pydantic-схемы, WebSocket
    clients.py dependencies.py      gRPC-клиенты, AuthCtx/AnonCtx
    errors.py middleware.py         маппинг ошибок, X-Request-ID
  auth/                           ← пользователи, argon2, JWT + refresh-сессии с ротацией
  example/                        ← образец: CRUD Item, вызов auth, consumer события
templates/service/                ← шаблон для make new-service
frontend/                         ← React + Vite + TS; в Docker — nginx, проксирующий /api и /ws
infra/ansible/                    ← деплой на сервер по IP
Dockerfile                        ← один образ на все Python-сервисы (build-arg PACKAGE)
scripts/                          ← gen_proto.py, new_service.py, smoke.py
docs/                             ← рецепты, соглашения, реестр событий
```

## 8. Все команды

| Команда | Что делает |
|---|---|
| `make install` | `.env` + `uv sync --all-packages` |
| `make proto` | Python-код из всех `.proto` |
| `make new-service name=x [entity=X] [port=N]` | каркас сервиса + регистрация везде |
| `make up` / `make up-kafka` | всё в Docker (без Kafka / с Kafka и kafka-ui) |
| `make down` / `make reset` | остановить / остановить и удалить данные |
| `make ps`, `make logs [s=gateway]` | статус, логи |
| `make infra` / `make infra-kafka` | только инфраструктура для локальной разработки |
| `make run s=<svc> [cmd=serve\|migrate]` | запустить сервис локально (по умолчанию migrate + serve) |
| `make migration s=<svc> m="msg"` | autogenerate миграции |
| `make front-dev` | фронт с hot reload |
| `make fmt` | автоформат и автофиксы ruff |
| `make lint`, `make typecheck`, `make test`, `make check` | проверки (check = всё, как в CI) |
| `make smoke [URL=...]` | сквозной тест живого стенда |
| `make server-setup HOST=... SSH_USER=...` | подготовить сервер (один раз) |
| `make deploy HOST=... SSH_USER=... [KAFKA=true]` | выкатить |

`make help` — то же самое в терминале.

## 9. Конфигурация (.env)

Один `.env` в корне читают и `docker compose`, и сервисы при локальном запуске. Остальные настройки — в
`config.py` каждого сервиса: у них дефолты под локальную разработку, в Docker их переопределяет `compose.yaml`.

| Переменная | По умолчанию | Зачем |
|---|---|---|
| `POSTGRES_PASSWORD` | `app` | пароль единственного Postgres |
| `JWT_SECRET` | dev-значение | подпись access-токенов (auth и gateway), ≥ 32 символов |
| `ADMIN_EMAILS` | `admin@example.com` | кто при регистрации получает роль admin |
| `KAFKA_ENABLED` | `false` | включить relay и consumer'ов (`make up-kafka` ставит сам) |
| `LOG_LEVEL` | `INFO` | уровень логов |
| `COOKIE_SECURE` | `false` | `true` только за HTTPS |
| `HTTP_PORT`, `GATEWAY_PORT`, `POSTGRES_PORT`, `REDIS_PORT` | 80, 8000, 5432, 6379 | поменяй, если порт занят |

Порты внутри:

| Что | Локально | На сервере |
|---|---|---|
| Фронт + прокси API | `:80` | `:80` — единственный открытый |
| Gateway / Swagger | `:8000` | через nginx: `/docs` |
| auth / example / новые | `127.0.0.1:50051 / 50052 / 50053…` | только внутри |
| Postgres / Redis | `127.0.0.1:5432 / 6379` | только внутри |
| Kafka / kafka-ui | `127.0.0.1:9094 / 8081` | только внутри |

## 10. Ошибки, права, пагинация

Ответ об ошибке всегда одинаковый, `details` — всегда массив:

```json
{"error": {"code": "SLOT_ALREADY_BOOKED", "message": "...", "request_id": "7f3c…", "details": []}}
{"error": {"code": "VALIDATION_ERROR", "message": "...", "request_id": "…",
           "details": [{"field": "title", "reason": "invalid_length"}]}}
```

Фронт принимает решения **только по `code`**. Недоступный сервис — 503 `SERVICE_UNAVAILABLE`, таймаут — 504,
необработанное исключение — 502 `UPSTREAM_ERROR` (текст исключения наружу не уходит, traceback в логах).

Права проверяются в обработчиках через контекст:

```python
ctx.require_user()                    # 401, если аноним; возвращает user_id
ctx.require_role("admin")             # 403, если роль не та
ctx.require_owner_or_admin(owner_id)  # 403, если не владелец и не админ
```

Пагинация: `?limit=20&cursor=…` → `{"items": [...], "next_cursor": "…" | null}`. В обработчике — `Page.from_request(...)`,
в репозиторий передаётся `limit + 1`, чтобы понять, есть ли следующая страница (см. `ListItemsHandler`).

Полная таблица кодов и маппинга — [docs/conventions.md](docs/conventions.md).

## 11. WebSocket

Подключение: `ws://<host>/ws/v1?token=<access_token>` (невалидный токен → close 4401).

```
→ {"type": "group.join", "request_id": "r1", "payload": {"group": "room:42"}}
← {"type": "group.join.ok", "request_id": "r1", "payload": {"group": "room:42"}}
← {"type": "error", "request_id": "r1", "payload": {"code": "...", "message": "...", "details": []}}
← {"type": "item.created", "request_id": null, "payload": {...}}       # push от сервера
```

Встроены: `ping`, `group.join`, `group.leave`, `group.say` (рассылка всем в группе), `item.get` (пример gRPC-вызова).
Своя команда — функция с декоратором `@ws_handler("type")` в `services/gateway/src/gateway/ws/handlers.py`:
что она вернёт, уйдёт клиенту как `<type>.ok`; ошибки gRPC и доменные превратятся в `error` автоматически.

Push из любой HTTP-ручки: `request.app.state.ws.send_to_user(user_id, type, payload)` или `.broadcast(group, type, payload)`.
На фронте — `connectWs(getAccessToken, onMessage)` из `frontend/src/api/ws.ts` (переподключается сам).
Ограничение: одна реплика gateway.

## 12. Kafka и события

По умолчанию Kafka выключена, но события всё равно пишутся в таблицу `outbox` той же транзакцией, что и данные.
`make up-kafka` поднимает Kafka и kafka-ui (http://localhost:8081), включает relay, и накопленные события уходят.

Опубликовать (в обработчике команды):

```python
uow.outbox.add("booking.events", "booking.slot_booked.v1", {"slot_id": str(slot.id)}, key=str(slot.id))
await uow.commit()
```

Подписаться (в другом сервисе) — по образцу example:
1. модель `class ProcessedEvent(ProcessedEventMixin, Base)` и миграция (защита от дублей);
2. `transport/kafka/handlers.py`: `async def on_slot_booked(session, event): ...` и словарь `HANDLERS`;
3. `KafkaEventConsumer(...)` в `background` в `container.py`.

Повторная доставка ничего не задвоит: `event_id` фиксируется в `processed_events` в той же транзакции.
Добавил событие — допиши строку в [docs/events.md](docs/events.md).

## 13. Тесты и CI

- Use case'ы тестируются на фейках (in-memory UoW и репозитории) — быстро и без БД. Образцы: `services/*/tests`.
- `services/example/tests/test_events_pg.py` — интеграционный с настоящим Postgres. Пропускается сам, если
  Postgres не запущен (`make infra`).
- Gateway тестируется с подменёнными gRPC-стабами: `services/gateway/tests`.
- `make smoke` гоняет сквозной сценарий по живому стенду — локально и после деплоя.

CI (`.github/workflows/ci.yml`) на каждый push: ruff, mypy `--strict`, pytest с Postgres, проверка, что
сгенерированный proto-код свежий, `docker compose config`, сборка фронта.

## 14. Деплой на сервер

Сервер: Ubuntu 22.04+ / Debian 12+, SSH-доступ пользователем с sudo. Подробно — [infra/ansible/README.md](infra/ansible/README.md).

```bash
make server-setup HOST=1.2.3.4 SSH_USER=ubuntu    # один раз: Docker, зеркало Docker Hub, firewall (22/80/443)
make deploy HOST=1.2.3.4 SSH_USER=ubuntu          # каждый раз: rsync → .env → docker compose up --build
make smoke URL=http://1.2.3.4
```

- Уезжает текущая рабочая папка, незакоммиченное тоже; git на сервере не нужен.
- Секреты (`POSTGRES_PASSWORD`, `JWT_SECRET`) генерируются при первом деплое и хранятся у тебя в
  `infra/ansible/.secrets/` (в `.gitignore`). Не удаляй их, иначе на сервере поменяется пароль БД.
- Настройки — `infra/ansible/playbooks/group_vars/all.yml`: порт, Kafka, админы, зеркала.
- Развернуть на машине, где сидишь (например, ноут на площадке) — в `infra/ansible/inventory.ini`
  раскомментируй `local ansible_connection=local` и запусти `make deploy`.
- Логи на сервере: `ssh ubuntu@1.2.3.4 'cd /opt/mp && docker compose logs -f --tail=100 gateway'`.

## 15. Отладка

- **Найти запрос во всех логах:** `request_id` есть в заголовке ответа `X-Request-ID` и в `error.request_id`;
  `make logs | grep <id>` покажет путь через gateway и все сервисы.
- **Кто лежит:** `curl localhost:8000/health/ready` → `{"auth": "up", "booking": "down", ...}`.
- **Дёрнуть gRPC напрямую** (reflection включён):
  ```bash
  grpcurl -plaintext localhost:50052 list
  grpcurl -plaintext -d '{"context":{"actor_user_id":"<uuid>","actor_role":"user"},"title":"x"}' \
    localhost:50052 contracts.example.v1.ExampleService/CreateItem
  ```
- **Посмотреть БД:** `docker compose exec postgres psql -U app -d booking`.
- **SQL в логах:** `DATABASE_ECHO=true make run s=booking`.
- Частые проблемы (порт занят, Docker Hub недоступен, миграции, refresh-cookie) — таблица в конце
  [docs/recipes.md](docs/recipes.md).

## 16. Как убрать образец example

Когда свои сервисы готовы:

1. Удалить `services/example/`, `contracts/example/`, `gateway/routers/items.py`, `gateway/schemas/items.py`.
2. Убрать строки про `example` в `gateway/config.py`, `gateway/clients.py`, `gateway/main.py`
   и обработчик `item.get` в `gateway/ws/handlers.py`.
3. Убрать блок `example:` и `EXAMPLE_GRPC_TARGET` в `compose.yaml`, строку в `mypy_path` в `pyproject.toml`.
4. Во фронте — `items` в `src/api/index.ts` и `ItemsPage`.
5. В `scripts/smoke.py` заменить проверки items на свои.
6. `make proto && uv sync --all-packages && make check`.

## 17. Залить в свой GitHub

```bash
git init -b main
make install                      # создаст uv.lock — его тоже коммитим
git add -A
git commit -m "MP: initial structure"
git remote add origin git@github.com:<you>/<repo>.git
git push -u origin main
```

`.env`, `.venv`, `node_modules` и секреты деплоя уже в `.gitignore`. После первого пуша CI запустится сам.
