# MP — микросервисы на gRPC за Gateway

Каркас для хакатона в стиле Casino Platform: отдельные сервисы, общие `.proto`-контракты, gateway на FastAPI.
Транспорт, авторизация, ошибки, Docker и деплой уже сделаны — на хакатоне пишем контракты и бизнес-логику.

```
Браузер ──HTTP/WS──▶ frontend (nginx :80) ──▶ gateway (FastAPI :8000) ──gRPC──▶ auth_service    :50051 ──▶ auth_db
                                                 JWT → RequestContext                example_service :50052 ──▶ example_db
                                                 ошибки gRPC → HTTP                    <ваш>_service  :50053 ──▶ <ваш>_db
```

**Работает из коробки:** регистрация, логин, refresh-токен в HttpOnly cookie, logout, `GET /users/me`;
образец CRUD-сервиса (`example_service`) с вызовом другого сервиса по gRPC; единый формат ошибок с кодами
из сервисов; `request_id` в логах; WebSocket с push-событиями; миграции при старте; фронт-заглушка;
скрипт создания нового сервиса; тесты; CI; деплой на сервер по IP одной командой.

---

## Содержание

1. [Установка](#1-установка)
2. [Первый запуск](#2-первый-запуск)
3. [Два режима работы](#3-два-режима-работы)
4. [Структура проекта](#4-структура-проекта)
5. [Как устроен сервис](#5-как-устроен-сервис)
6. [Как проходит запрос](#6-как-проходит-запрос)
7. [Гайд: от ТЗ до фичи](#7-гайд-от-тз-до-фичи)
8. [Новый сервис](#8-новый-сервис)
9. [Вызов другого сервиса](#9-вызов-другого-сервиса)
10. [Ошибки, права, пагинация](#10-ошибки-права-пагинация)
11. [WebSocket](#11-websocket)
12. [Все команды](#12-все-команды)
13. [Конфигурация и порты](#13-конфигурация-и-порты)
14. [Тесты и CI](#14-тесты-и-ci)
15. [Деплой](#15-деплой)
16. [Отладка и частые проблемы](#16-отладка-и-частые-проблемы)
17. [Работа в команде](#17-работа-в-команде)
18. [Как убрать example_service](#18-как-убрать-example_service)
19. [Залить в свой GitHub](#19-залить-в-свой-github)

---

## 1. Установка

Нужно: **Python 3.13**, **[uv](https://docs.astral.sh/uv/)**, **Docker + compose + buildx**, **Node 22** (фронт локально),
**Ansible + rsync** (только для деплоя).

```bash
# Arch
sudo pacman -S python uv docker docker-compose docker-buildx nodejs npm ansible rsync
sudo systemctl enable --now docker
sudo usermod -aG docker $USER        # и перелогиниться
```

## 2. Первый запуск

```bash
make install     # .env из .env.example + uv sync в каждом сервисе (создаст uv.lock — коммитим)
make up          # собрать и поднять всё в Docker
make smoke       # сквозная проверка: register → login → items → refresh → logout
```

| Что | Адрес |
|---|---|
| Фронт | http://localhost |
| Swagger | http://localhost:8000/docs |
| Готовность сервисов | http://localhost:8000/health/ready |

В Swagger: `POST /api/v1/auth/register` → скопировать `access_token` → кнопка **Authorize** → дальше любые ручки.
Админом становится email из `ADMIN_EMAILS` в `.env` (по умолчанию `admin@example.com`).

`make down` — остановить (данные остаются), `make reset` — снести вместе с данными.

## 3. Два режима работы

**Всё в Docker** (`make up`) — для демо, проверки перед деплоем и для фронтендера. После правок кода — снова `make up`.

**Локально** — быстрее, видно логи, работает отладчик:

```bash
make db                         # только базы (auth_db, example_db, ...) в Docker
make run s=auth_service         # терминал 1: миграции + сервер
make run s=example_service      # терминал 2
make run s=gateway              # терминал 3, с --reload → http://localhost:8000/docs
make front-dev                  # терминал 4 → http://localhost:5173 (hot reload)
```

Настройки по умолчанию в `infra/config.py` каждого сервиса уже смотрят на `localhost` и порты баз из compose,
поэтому `.env` для локального запуска не обязателен. Нужно поменять — `cp .env.example .env` в папке сервиса.

Если тот же сервис уже запущен в Docker, порт занят: `docker compose stop auth_service`.

Каждый сервис — отдельный uv-проект. В IDE открывай папку сервиса (или добавь все в workspace),
интерпретатор — `services/<сервис>/.venv/bin/python`.

## 4. Структура проекта

```
contracts/                        ← .proto — контракты между сервисами (пишем руками)
  common/v1/common.proto            RequestContext — общий для всех
  auth/v1/auth_service.proto
  example/v1/example_service.proto
packages/platform_contracts/      ← сгенерированный Python из .proto (make proto, руками не трогаем)
services/
  gateway/                        ← HTTP + WebSocket, единственный вход снаружи
  auth_service/                   ← пользователи, пароли, JWT, refresh-сессии
  example_service/                ← образец: CRUD Item + вызов auth_service
scripts/
  generate_proto.py               ← make proto
  new_service.py                  ← make new-service
  smoke.py                        ← make smoke
frontend/                         ← React + Vite + TS; в Docker — nginx, проксирует /api и /ws в gateway
infra/ansible/                    ← деплой: роли common → docker → sync → env → start
compose.yaml                      ← всё вместе: frontend, gateway, сервисы и у каждого своя БД
```

## 5. Как устроен сервис

Все сервисы одинаковые, как `identity_service` в Casino Platform:

```
services/example_service/
  pyproject.toml  uv.lock  Dockerfile  alembic.ini  .env.example
  migrations/                         ← alembic (env.py берёт DATABASE_URL из Settings)
  src/example_service/
    main.py                           ← точка входа: логи + asyncio.run(serve())
    dependencies.py                   ← composition root: собирает UoW, клиенты, регистрирует хэндлеры
    applications/
      mediator.py                     ← Command / Mediator
      context.py                      ← RequestContext: кто делает запрос + require_user / require_owner_or_admin
      exceptions.py                   ← ошибки уровня приложения (NotFound, PermissionDenied...)
      commands/                       ← что хотим изменить:  CreateItemCommand(ctx, title, ...)
      queries/                        ← что хотим прочитать: GetItemQuery(ctx, item_id)
      handlers/                       ← как это сделать:     CreateItemCommandHandler.handle()
      ports/                          ← интерфейсы (Protocol): репозитории, UnitOfWork, клиенты других сервисов
      results/                        ← read models — что возвращают хэндлеры
    domain/
      entities.py                     ← сущности и их поведение (Item.edit, Item.change_status)
      value_objects.py                ← ItemTitle с валидацией
      exceptions.py                   ← доменные ошибки
    infra/
      config.py                       ← Settings (pydantic-settings)
      database/                       ← Base, engine, модели SQLAlchemy
      repositories/                   ← реализация портов: модель ⇄ сущность
      uow/                            ← SQLAlchemyUnitOfWork
      clients/                        ← gRPC-клиенты к другим сервисам
    transport/grpc/
      server.py                       ← gRPC-сервер + health + reflection
      servicer.py                     ← proto → команда → mediator → proto
      mappers.py                      ← proto ⇄ read model, контекст из proto
      errors.py                       ← @grpc_errors + таблица ERROR_CODES
  tests/                              ← хэндлеры на фейках (fakes.py), без БД
```

Правило слоёв: `domain` ничего не знает про БД и gRPC; `applications` знает только про порты (Protocol);
реализации — в `infra`; `transport` только переводит proto в команды и обратно; всё связывается в `dependencies.py`.

## 6. Как проходит запрос

`GET /api/v1/items/{id}`:

1. **nginx** (`frontend/nginx.conf`) проксирует `/api` в gateway.
2. **gateway**: middleware ставит `X-Request-ID`; зависимость `AuthCtx` проверяет JWT и собирает
   `RequestContext{request_id, actor_user_id, actor_role}`; роутер `routers/items.py` вызывает
   `clients.example.GetItem(pb.GetItemRequest(context=ctx, item_id=...))`.
3. **example_service**: servicer → `GetItemQuery` → `mediator.send` → `GetItemQueryHandler`: берёт Item через
   UnitOfWork, проверяет `ctx.require_owner_or_admin`, вызывает auth_service за именем владельца.
4. Если брошено `ItemNotFoundError`, `@grpc_errors` по таблице `ERROR_CODES` отвечает `NOT_FOUND` и кладёт
   в trailing metadata `error-code: ITEM_NOT_FOUND`. Gateway (`errors.py`) превращает это в
   `404 {"error": {"code": "ITEM_NOT_FOUND", ...}}`.

Ни в роутерах, ни в servicer'ах нет try/except: ошибки обрабатываются в одном месте.

## 7. Гайд: от ТЗ до фичи

Пример ТЗ: «пользователь бронирует слот; занятый слот забронировать нельзя».

### 7.1. Разбор (вся команда, 30–60 минут)

- Сценарии глаголами: «создать слот», «забронировать», «мои брони».
- Кто владеет какими данными. Один сервис = одна зона ответственности и своя БД. Обычно хватает 2–4 сервисов, auth уже есть.
- Какие вызовы между сервисами нужны (gRPC, синхронно).
- HTTP API для фронта — договориться сразу, фронтендер начинает параллельно.

### 7.2. Создать сервис

```bash
make new-service name=booking entity=Slot
```

Скопирует `example_service` в `services/booking_service`, переименует Item → Slot, выберет свободные порты
и напечатает, что дописать в compose, gateway и CI (подробно — [раздел 8](#8-новый-сервис)).

### 7.3. Контракт — `contracts/booking/v1/booking_service.proto`

```proto
service BookingService {
  rpc CreateSlot(CreateSlotRequest) returns (CreateSlotResponse);
  rpc BookSlot(BookSlotRequest) returns (BookSlotResponse);          // новое
  ...
}

message BookSlotRequest {
  common.v1.RequestContext context = 1;       // первое поле каждого запроса
  string slot_id = 2;
}
message BookSlotResponse { Slot slot = 1; }
```

```bash
make proto
```

Правила: RPC `Foo` → `FooRequest` / `FooResponse`; у enum нулевое значение `*_UNSPECIFIED`;
«не менять» в update — `optional`; номера полей не переиспользуем.

### 7.4. Домен — `domain/entities.py`, `domain/exceptions.py`

```python
class SlotAlreadyBookedError(SlotDomainError):
    pass


@dataclass(slots=True, kw_only=True)
class Slot:
    ...
    booked_by: UUID | None = None

    def book(self, user_id: UUID) -> None:
        if self.booked_by is not None:
            raise SlotAlreadyBookedError("Slot is already booked")
        self.booked_by = user_id
        self.updated_at = utc_now()
```

### 7.5. Команда и хэндлер

`applications/commands/book_slot.py`:

```python
@dataclass(frozen=True)
class BookSlotCommand(Command[SlotReadModel]):
    ctx: RequestContext
    slot_id: UUID
```

`applications/handlers/book_slot.py`:

```python
@dataclass
class BookSlotCommandHandler:
    uow_factory: UnitOfWorkFactory

    async def handle(self, cmd: BookSlotCommand) -> SlotReadModel:
        user_id = cmd.ctx.require_user()

        async with self.uow_factory() as uow:
            slot = await uow.slots.get_by_id(cmd.slot_id)
            if slot is None:
                raise SlotNotFoundError("Slot not found")

            slot.book(user_id)              # правило — в домене

            await uow.slots.save(slot)
            await uow.commit()              # без commit всё откатится

        return SlotReadModel.from_slot(slot)
```

Регистрация в `dependencies.py`:

```python
mediator.register(BookSlotCommand, BookSlotCommandHandler(uow_factory=uow_factory))
```

### 7.6. Модель и миграция

Колонка в `infra/database/models.py` (`booked_by: Mapped[uuid.UUID | None]`), маппинг в
`infra/repositories/slot_repository.py` (`_to_model`, `_to_domain`, `save`), затем:

```bash
make db
make migration s=booking_service m="slot booked_by"     # → migrations/versions/
```

Проверь файл глазами. Применится при старте сервиса (`alembic upgrade head` в Dockerfile и в `make run`).

### 7.7. Ошибка → код для фронта — `transport/grpc/errors.py`

```python
ERROR_CODES = [
    ...
    (SlotAlreadyBookedError, grpc.StatusCode.FAILED_PRECONDITION, "SLOT_ALREADY_BOOKED"),  # → HTTP 409
]
```

### 7.8. Servicer — `transport/grpc/servicer.py`

```python
@grpc_errors
async def BookSlot(self, request: pb.BookSlotRequest, context: Context) -> pb.BookSlotResponse:
    slot = await self._mediator.send(
        BookSlotCommand(ctx=context_from_proto(request.context), slot_id=parse_slot_id(request.slot_id))
    )
    return pb.BookSlotResponse(slot=slot_to_proto(slot))
```

### 7.9. Ручка в gateway — `services/gateway/src/gateway/routers/booking.py`

```python
@router.post("/{slot_id}/book")
async def book_slot(slot_id: UUID, ctx: AuthCtx, clients: Clients) -> SlotOut:
    result = await clients.booking.BookSlot(pb.BookSlotRequest(context=ctx, slot_id=str(slot_id)))
    return SlotOut.from_proto(result.slot)
```

`AuthCtx` — нужен логин, `AnonCtx` — можно без него. Схемы `SlotOut` — в `schemas/booking.py` по образцу `schemas/items.py`.

### 7.10. Тест — `tests/test_slots.py`

Фейковые UoW и репозиторий уже в `tests/fakes.py`:

```python
async def test_cannot_book_twice(mediator: Mediator) -> None:
    slot = await mediator.send(CreateSlotCommand(ctx(ALICE), "10:00"))
    await mediator.send(BookSlotCommand(ctx(ALICE), slot.id))
    with pytest.raises(SlotAlreadyBookedError):
        await mediator.send(BookSlotCommand(ctx(BOB), slot.id))
```

```bash
make check       # ruff + mypy --strict + pytest во всех сервисах
```

### 7.11. Фронт

`frontend/src/api/index.ts` — по образцу `items`:

```ts
export const slots = {
  list: (offset = 0) => request<Page<Slot>>("GET", `/booking?offset=${offset}`),
  book: (id: string) => request<Slot>("POST", `/booking/${id}/book`),
};
```

`request()` сам подставляет токен, на 401 обновляет его через refresh-cookie и повторяет запрос, ошибку
бросает как `ApiError` с полем `code`. Экран — по образцу `src/pages/ItemsPage.tsx`.

### 7.12. Выкатить

```bash
make up && make smoke                         # локально
make deploy HOST=<ip> SSH_USER=<user>         # на сервер
make smoke URL=http://<ip>
```

## 8. Новый сервис

```bash
make new-service name=orders                       # копия example_service, сущность остаётся Item
make new-service name=orders entity=Order          # + Item → Order, items → orders во всём коде
make new-service name=orders entity=Order port=50060 db_port=5440
```

Скрипт создаёт `contracts/orders/` и `services/orders_service/` (порты и БД уже свои) и **ничего больше не трогает**.
Остальное дописываешь сам — скрипт печатает готовые куски:

1. `compose.yaml` — блоки `orders_service` и `orders_db`, volume, у gateway — `ORDERS_GRPC_TARGET` и `depends_on`.
2. gateway: адрес в `config.py`, стаб в `grpc_clients.py`, роутер `routers/orders.py` (копия `items.py`) + `include_router` в `main.py`.
3. CI: `orders_service` в `matrix.service`; деплой: `ORDERS_DB_PASSWORD` в `infra/ansible/roles/env/templates/env.j2` и `.env.example`.
4. `make proto && make install && make up`.

Если сервису не нужен auth — удали `infra/clients/auth_client.py`, `applications/ports/user_directory.py`
и их использование в `dependencies.py` и `handlers/get_*.py`.

## 9. Вызов другого сервиса

Образец — `example_service` ходит в `auth_service` за именем владельца:

| Что | Где |
|---|---|
| Интерфейс | `applications/ports/user_directory.py` — `UserDirectory(Protocol)` |
| Реализация | `infra/clients/auth_client.py` — `GrpcUserDirectory`: stub + таймаут + тот же RequestContext |
| Адрес | `infra/config.py` — `auth_grpc_target`; в compose — `AUTH_GRPC_TARGET: auth_service:50051` |
| Сборка | `dependencies.py` — канал `grpc.aio.insecure_channel(...)`, закрывается в `Container.close()` |
| Использование | `handlers/get_item.py` — `await self.users.get_name(ctx, owner_id)` |

Ошибка соседа: либо деградируем (как здесь — отдаём item без имени), либо бросаем своё исключение.
Вызов делаем **вне** открытой транзакции UnitOfWork.

## 10. Ошибки, права, пагинация

**Ответ об ошибке** всегда одинаковый:

```json
{"error": {"code": "ITEM_NOT_FOUND", "message": "Item not found", "request_id": "7f3c…", "details": []}}
```

Фронт решает только по `code`. Откуда берётся:

| В сервисе (`ERROR_CODES`) | gRPC | HTTP |
|---|---|---|
| `INVALID_ARGUMENT` | ошибка валидации | 422 |
| `UNAUTHENTICATED` | нет логина / плохой пароль | 401 |
| `PERMISSION_DENIED` | чужой ресурс | 403 |
| `NOT_FOUND` | не найдено | 404 |
| `ALREADY_EXISTS` | дубликат | 409 |
| `FAILED_PRECONDITION` | нельзя в текущем состоянии | 409 |
| сервис не отвечает | `UNAVAILABLE` / `DEADLINE_EXCEEDED` | 503 / 504 |
| исключение не из таблицы | `INTERNAL` | 502 `UPSTREAM_ERROR`, текст скрыт, traceback в логах сервиса |

Ошибка прямо из роутера gateway: `raise ApiError(400, "BAD_REQUEST", "...")`.

**Права** — в хэндлерах через контекст:

```python
user_id = cmd.ctx.require_user()                # 401, если аноним
cmd.ctx.require_owner_or_admin(item.owner_id)   # 403, если не владелец и не админ
cmd.ctx.is_admin
```

**Пагинация**: `?limit=20&offset=0` → `{"items": [...], "has_more": true}`. Хэндлер запрашивает `limit + 1`
строк, чтобы узнать, есть ли следующая страница (`handlers/list_items.py`).

## 11. WebSocket

`ws://<host>/ws/v1?token=<access_token>` (невалидный токен → close 4401). Сервер шлёт `{"type": ..., "payload": ...}`,
клиент может прислать `{"type": "ping"}` → `pong`.

Push из любого роутера gateway:

```python
await request.app.state.ws.send_to_user(user_id, "item.created", {...})
await request.app.state.ws.broadcast("slot.booked", {...})
```

На фронте — `connectWs(getAccessToken, onMessage)` из `frontend/src/api/ws.ts` (переподключается сам).
Код — `services/gateway/src/gateway/ws.py`. Ограничение: одна реплика gateway.

## 12. Все команды

| Команда | Что делает |
|---|---|
| `make install` | `.env` + `uv sync` в каждом сервисе |
| `make lock` | `uv lock` в каждом сервисе |
| `make proto` | Python из `contracts/**/*.proto` |
| `make new-service name=x [entity=X] [port=N] [db_port=N]` | копия example_service |
| `make up` / `make down` / `make reset` | поднять / остановить / остановить и удалить данные |
| `make ps`, `make logs [s=gateway]` | статус, логи |
| `make db` | только базы — для локального запуска |
| `make run s=<сервис>` | запустить сервис локально (миграции + сервер) |
| `make migration s=<сервис> m="msg"` | новая миграция (autogenerate) |
| `make front-dev` | фронт с hot reload |
| `make fmt` / `make lint` / `make typecheck` / `make test` / `make check` | качество кода |
| `make smoke [URL=...]` | сквозной тест живого стенда |
| `make deploy HOST=... SSH_USER=...` | выкатить на сервер |

## 13. Конфигурация и порты

Корневой `.env` читает `docker compose`:

| Переменная | Зачем |
|---|---|
| `JWT_SECRET` | общий секрет: auth_service подписывает токены, gateway проверяет (≥ 32 символов) |
| `ADMIN_EMAILS` | кто при регистрации получает роль admin |
| `AUTH_DB_PASSWORD`, `EXAMPLE_DB_PASSWORD` | пароли баз |
| `COOKIE_SECURE` | `true` только за HTTPS |
| `HTTP_PORT` | порт фронта на хосте |

Настройки сервиса — `services/<сервис>/src/<сервис>/infra/config.py` (Settings), для локального запуска
можно переопределить через `services/<сервис>/.env`.

| Что | Порт | Наружу на сервере |
|---|---|---|
| frontend (nginx) | 80 | да — единственный |
| gateway / Swagger | 8000 | через nginx: `/api`, `/ws`, `/docs` |
| auth_service / example_service / новые | 50051 / 50052 / 50053… | нет (127.0.0.1) |
| auth_db / example_db / новые | 5433 / 5434 / 5435… | нет (127.0.0.1) |

## 14. Тесты и CI

- Хэндлеры тестируются на фейках (`tests/fakes.py`): in-memory репозитории и UnitOfWork, без БД.
- Gateway тестируется с подменёнными gRPC-стабами (`services/gateway/tests`).
- `make smoke` — сквозной сценарий по живому стенду, локально и после деплоя.

CI (`.github/workflows/ci.yml`), на каждый push: для каждого сервиса ruff, mypy `--strict`, pytest; проверка,
что сгенерированный proto-код свежий; `docker compose config`; сборка фронта.

## 15. Деплой

Сервер: Ubuntu 22.04+ / Debian 12+, SSH пользователем с sudo.

```bash
make deploy HOST=1.2.3.4 SSH_USER=ubuntu
make smoke URL=http://1.2.3.4
```

Роли по порядку: `common` (пакеты) → `docker` (Docker из репозиториев дистрибутива + зеркало Docker Hub) →
`sync` (rsync текущей папки в `/opt/mp`, git на сервере не нужен) → `env` (`.env` с паролями, которые
генерируются один раз и хранятся в `infra/ansible/.secrets/`) → `start` (`docker compose up -d --build`, ждёт `/health/ready`).

Подробности и настройки — [infra/ansible/README.md](infra/ansible/README.md).

## 16. Отладка и частые проблемы

- **Найти запрос в логах:** `request_id` есть в заголовке `X-Request-ID` и в `error.request_id`; сервисы пишут его в лог.
- **Кто лежит:** `curl localhost:8000/health/ready`.
- **Дёрнуть gRPC напрямую** (reflection включён):
  ```bash
  grpcurl -plaintext localhost:50052 list
  grpcurl -plaintext -d '{"context":{"actor_user_id":"<uuid>","actor_role":"user"},"title":"x"}' \
    localhost:50052 example.v1.ExampleService/CreateItem
  ```
- **Посмотреть БД:** `docker compose exec example_db psql -U example -d example`.

| Симптом | Что делать |
|---|---|
| `port is already allocated` | занят 80 → `HTTP_PORT=8080` в `.env`; занят порт БД — поменяй в `compose.yaml` и в `infra/config.py` сервиса |
| `503 SERVICE_UNAVAILABLE` | сервис не запущен: `make ps`, `make logs s=<сервис>` |
| `502 UPSTREAM_ERROR` | исключение не из `ERROR_CODES` — traceback в логах сервиса |
| ручка не видит новый RPC | забыл `make proto` (в Docker — ещё `make up`) |
| таблицы нет | миграцию не создали: `make migration s=... m=...` |
| Docker Hub не качается | `"registry-mirrors": ["https://mirror.gcr.io"]` в `/etc/docker/daemon.json` (на сервере ставит Ansible) |
| refresh не работает на сервере | по HTTP должно быть `COOKIE_SECURE=false` |

## 17. Работа в команде

| Кто | Где |
|---|---|
| Тимлид / DevOps | `compose.yaml`, `infra/`, CI, `make new-service`, gateway (`config`, `grpc_clients`, `main`) |
| Бэкенд | `services/<свой>_service/`, свой роутер в `gateway/routers/` |
| Фронтенд | `frontend/`, работает по Swagger от `make up` |

- **Контракт — точка синхронизации:** сначала PR с `.proto` + `make proto`, потом реализация.
- `make new-service` запускает один человек и сразу пушит — правки compose и gateway общие.
- `packages/platform_contracts` (сгенерированный код) коммитится, CI проверяет, что он свежий.
- Перед пушем — `make fmt && make check`.

## 18. Как убрать example_service

1. Удалить `services/example_service/`, `contracts/example/`, `gateway/routers/items.py`, `gateway/schemas/items.py`.
2. Убрать `example` из `gateway/config.py`, `gateway/grpc_clients.py`, `gateway/main.py`.
3. Убрать `example_service`, `example_db`, volume и `EXAMPLE_GRPC_TARGET` из `compose.yaml`; `EXAMPLE_DB_PASSWORD`
   из `.env.example` и `infra/ansible/roles/env/templates/env.j2`; сервис из CI.
4. Во фронте — `items` в `src/api/index.ts` и `ItemsPage`; в `scripts/smoke.py` — проверки items.
5. `make proto && make check`.

Сначала сделай свой сервис через `make new-service`: он копирует именно `example_service`.

## 19. Залить в свой GitHub

```bash
git init -b main
make install                     # создаст uv.lock в сервисах — их тоже коммитим
git add -A
git commit -m "MP: initial structure"
git remote add origin git@github.com:<you>/<repo>.git
git push -u origin main
```

`.env`, `.venv`, `node_modules`, секреты деплоя — в `.gitignore`.
