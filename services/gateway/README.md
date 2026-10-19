# gateway

Единственный HTTP-вход. Владелец — TL. Логики нет: HTTP-схема → proto → gRPC → proto → HTTP-схема.

- Контракт с фронтом — `contracts/http/openapi.yaml` (читать в `docs/API.md`). Схемы в `schemas/` —
  один к одному с ним; enum'ы HTTP ⇄ proto — только в `schemas/enums.py`.
- `/api/v1/platforms` → collector, `/api/v1/query/analyze` → ml, остальное → search.
- Авторизации нет (по ТЗ): `Ctx` несёт только `request_id`.
- Ошибки сервисов: gRPC-статус + `error-code` → `{"error": {code, message, request_id, details}}`
  (`errors.py`). `UNIMPLEMENTED` → 501 `NOT_IMPLEMENTED`; сообщение «<поле>: <текст>» у
  `SEARCH_INVALID_PARAMS` / `VALIDATION_ERROR` → `details: [{field, message}]`.

Swagger: http://localhost:8000/docs. Порт 8000.
