# Реестр событий

| Тип | Топик | Producer | Consumers | Payload |
|---|---|---|---|---|
| `auth.user_registered.v1` | `auth.events` | auth (RegisterUser) | example (создаёт welcome-item) | `{user_id, email, name}` |

Конверт (общий для всех, `platform_common.kafka.events.Event`):

```json
{"id": "uuid", "type": "auth.user_registered.v1", "producer": "auth",
 "occurred_at": "2026-10-18T12:00:00+00:00", "payload": {...}}
```

Ключ сообщения — id агрегата (порядок событий одного агрегата сохраняется в партиции).

Добавил событие — добавь строку сюда.
