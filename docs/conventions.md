# Соглашения

## 1. Поток запроса

```
HTTP → RequestIdMiddleware (X-Request-ID) → роутер gateway
     → Depends(AuthCtx): JWT → RequestContext{request_id, actor_user_id, actor_role}
     → stub.Method(Request(context=ctx, ...))           # таймаут и x-request-id ставит канал
       → @rpc servicer: request_id в логи, AppError → gRPC status + x-error-code
         → mediator.send(Command(ctx, ...)) → Handler → UoW/репозитории → domain
     ← AioRpcError? → обработчик в gateway/errors.py → HTTP JSON единого формата
```

Роутеры и servicer'ы **не содержат try/except** — ошибки маппятся централизованно.

## 2. Ошибки

В домене/приложении бросаем наследника базовой ошибки с публичным `code`:

```python
class OrderNotFoundError(NotFoundError):
    code = "ORDER_NOT_FOUND"


raise ValidationError(details=[ErrorDetail("title", "too_long")])
raise ValidationError.field("email", "invalid_format")
```

| Базовый класс (`platform_common.errors`) | gRPC | HTTP | code по умолчанию |
|---|---|---|---|
| `ValidationError` | INVALID_ARGUMENT | 422 | VALIDATION_ERROR |
| `UnauthenticatedError` | UNAUTHENTICATED | 401 | UNAUTHENTICATED |
| `PermissionDeniedError` | PERMISSION_DENIED | 403 | PERMISSION_DENIED |
| `NotFoundError` | NOT_FOUND | 404 | NOT_FOUND |
| `AlreadyExistsError` | ALREADY_EXISTS | 409 | ALREADY_EXISTS |
| `ConflictError` | FAILED_PRECONDITION | 409 | INVALID_STATE_TRANSITION |
| `RateLimitedError` | RESOURCE_EXHAUSTED | 429 | RATE_LIMITED |
| `UnavailableError` | UNAVAILABLE | 503 | SERVICE_UNAVAILABLE |
| любое другое исключение | INTERNAL | 502 | UPSTREAM_ERROR (текст скрыт) |

Ответ Gateway всегда такой (`details` — всегда массив):

```json
{"error": {"code": "ITEM_IS_DONE", "message": "...", "request_id": "uuid", "details": []}}
```

Фронт принимает решения **только по `code`**, `message` — для разработчиков.

## 3. RequestContext и права

- Заполняет только Gateway из проверенного JWT. Клиентские actor-поля не принимаются.
- В сервисе: `ctx = RequestContext.from_proto(request.context)` и дальше в команду.
- Проверки: `ctx.require_user()`, `ctx.require_role("admin")`, `ctx.require_owner_or_admin(owner_id)`.
- Сервис → сервис: передаём тот же контекст — `ctx.to_proto()`.
- Роли — строки (`user`, `admin`). Админы задаются через `ADMIN_EMAILS` в `.env`.

## 4. HTTP API (Gateway)

- База `/api/v1`, JSON в `snake_case`, время RFC 3339 UTC, UUID строками.
- Авторизация: `Authorization: Bearer <access>`; access живёт 15 минут.
- Refresh-токен — только HttpOnly cookie `refresh_token` (path `/api/v1/auth`), ротируется на каждом `/auth/refresh`.
- Пагинация: `?limit=20&cursor=...` → `{"items": [...], "next_cursor": "..." | null}`.
- `X-Request-ID` принимается от клиента или генерируется, возвращается в ответе и пишется во все логи.
- Swagger: `/docs` (кнопка Authorize принимает access-токен).

| Метод | Путь | |
|---|---|---|
| POST | `/auth/register` | `{email, name, password}` → 201 `{access_token, user, ...}` + cookie |
| POST | `/auth/login` | rate limit 10/мин на IP |
| POST | `/auth/refresh` | по cookie → новый access + новая cookie |
| POST | `/auth/logout` | 204, отзывает refresh |
| GET | `/users/me`, `/users/{id}` | чужой email видит только admin |
| POST/GET/PATCH/DELETE | `/items`, `/items/{id}` | образец CRUD |
| GET | `/health/live`, `/health/ready` | ready проверяет gRPC health всех сервисов + Redis |

## 5. WebSocket

`ws(s)://<host>/ws/v1?token=<access_token>` (невалидный токен → close 4401).

```
→ {"type": "group.join", "request_id": "r1", "payload": {"group": "room:42"}}
← {"type": "group.join.ok", "request_id": "r1", "payload": {"group": "room:42"}}
← {"type": "error", "request_id": "r1", "payload": {"code": "...", "message": "...", "details": []}}
← {"type": "item.created", "request_id": null, "payload": {...}}     # push от сервера
```

Встроенные команды: `ping`, `group.join`, `group.leave`, `group.say`, `item.get`.
Push из HTTP-ручки: `await request.app.state.ws.send_to_user(user_id, "type", payload)` или `.broadcast(group, ...)`.
Ограничение: одна реплика gateway (для нескольких — Redis pub/sub, интерфейс тот же).

## 6. Сервис внутри

- `domain/` — dataclass-сущности и правила. Ничего не знает про БД/gRPC/HTTP.
- `application/` — `Command`/`Query` + `Handler`, порты как `Protocol`. Транзакция = `async with uow: ... await uow.commit()`.
- `infra/` — модели SQLAlchemy, репозитории (маппинг модель ⇄ домен), UoW, клиенты соседей.
- `transport/` — тонкие адаптеры: proto ⇄ команды.
- `container.py` — единственное место, где реализации связываются с портами (тесты подменяют их фейками).
- Каждый сервис владеет своей БД (`database_name` в Settings, создаётся при старте). В чужие БД не ходим.

## 7. Proto

- Файл: `contracts/<svc>/v1/<svc>.proto`, пакет `contracts.<svc>.v1`, сервис `<Svc>Service`.
- Первое поле каждого запроса — `contracts.common.v1.RequestContext context = 1;`.
- RPC `Foo` → `FooRequest` / `FooResponse` (требование buf lint).
- Enum: нулевое значение `<ENUM>_UNSPECIFIED = 0`.
- «Не менять» в update → `optional` поля (`HasField`).
- Номера полей не переиспользуем; удалили поле → `reserved`.

## 8. События (Kafka)

- Имя: `<домен>.<событие>.v<N>` (`auth.user_registered.v1`), топик: `<домен>.events`.
- Публикуем только через outbox: `uow.outbox.add(topic, type, payload, key=...)` в той же транзакции.
- Consumer — идемпотентный (`processed_events`), обработчик получает сессию той же транзакции.
- Реестр событий — `docs/events.md`.
