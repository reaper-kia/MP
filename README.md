# MP — медиамониторинг соцсетей

Кейс финала Первенства России по продуктовому программированию: сотрудник агентства одним полем
задаёт тему / событие / человека / текст новости, выбирает период и источники, получает подборку
**реальных** публикаций VK / OK / MAX с прямыми ссылками и выгружает XLSX.

- Архитектура и правила продукта — [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Задачи по ролям — [`docs/tasks/`](docs/tasks/README.md)
- HTTP API для фронта — [`docs/API.md`](docs/API.md) (источник: `contracts/http/openapi.yaml`)
- gRPC между сервисами — [`docs/GRPC.md`](docs/GRPC.md) (источник: `contracts/*/v1/*.proto`)

```
Браузер / расширение ──HTTP──▶ frontend (nginx :80) ──▶ gateway (FastAPI :8000)
                                                          │ gRPC
              ┌───────────────────────────────────────────┼──────────────────────┐
              ▼                                           ▼                      ▼
   search_service :50053 ──gRPC──▶ collector_service :50054        ml_service :50055
   источники, поиски, подборка,    VK / OK / MAX / сайты            разбор запроса, отбор,
   дедуп, экспорт  ──▶ search_db   (без БД)                          группы (без БД)
              └──────────────────────gRPC──────────────────────────────▲
```

| Сервис | Владелец | Порт | Что внутри |
|---|---|---|---|
| `gateway` | TL | 8000 | HTTP-схемы по `openapi.yaml`, маппинг ошибок; `/platforms` → collector, `/query/analyze` → ml, остальное → search |
| `search_service` | B2 | 50053, БД 5435 | CQRS по шаблону: команды/запросы, хэндлеры, UoW, клиенты collector и ml |
| `collector_service` | B1 | 50054 | коннекторы площадок + общие гарантии (период, дубли, лимиты); `COLLECTOR_FAKE=true` — тестовые посты |
| `ml_service` | ML | 50055 | `core/` (чистая логика) + провайдеры LLM/эмбеддингов (stub / ollama / yandex) |
| `frontend` | FE | 80 | React + Vite + TS; моки — `make mock` (Prism) или MSW |

Авторизации нет — по ТЗ регистрация не нужна.

## Запуск

Нужно: Python 3.13, [uv](https://docs.astral.sh/uv/), Docker + compose + buildx, Node 22,
Ansible + rsync (только деплой).

```bash
make install     # .env из .env.example + uv sync в каждом сервисе
make proto       # код из contracts/*.proto + справочники docs/ (после КАЖДОЙ правки контракта)
make up          # всё в Docker: фронт http://localhost, Swagger http://localhost:8000/docs
make smoke       # сквозной сценарий: площадки → источник → поиск → подборка → XLSX
```

`make down` — остановить, `make reset` — вместе с данными БД.

Локально, с отладчиком и hot reload:

```bash
make db                          # только search_db в Docker
make run s=collector_service     # терминал 1  (COLLECTOR_FAKE=true в services/collector_service/.env)
make run s=ml_service            # терминал 2
make run s=search_service        # терминал 3  (миграции + сервер)
make run s=gateway               # терминал 4  → http://localhost:8000/docs
make front-dev                   # терминал 5  → http://localhost:5173
make mock                        # фронт без бэкенда: мок по openapi.yaml на :4010
```

Локальная LLM без ключей Яндекса: `docker compose --profile llm-local up -d ollama`, затем
`LLM_PROVIDER=ollama` для ml_service.

## Как добавить / поменять RPC (контракт — точка синхронизации)

1. Правка `.proto` (и `openapi.yaml`, если меняется HTTP) — через TL.
2. `make proto` → коммит `packages/platform_contracts` и `docs/` (CI проверяет, что всё свежее).
3. Сервис: команда/запрос → хэндлер → регистрация в `dependencies.py` → метод servicer'а → маппер.
4. Ошибка = строка в `ERROR_CODES` (`transport/grpc/errors.py`); gateway отдаёт её код фронту.
5. Gateway: схема в `schemas/`, ручка в `routers/`.
6. `make fmt && make check`.

Пока сценарий не написан, хэндлер бросает `NotImplementedYetError` → gRPC `UNIMPLEMENTED` →
HTTP **501 `NOT_IMPLEMENTED`** с номером задачи в сообщении.

## Команды

| Команда | Что делает |
|---|---|
| `make install` / `make lock` | `uv sync` / `uv lock` в каждом сервисе |
| `make proto` | Python из `contracts/**/*.proto` + `make docs` |
| `make docs` | `docs/API.md`, `docs/api-types.ts`, `docs/GRPC.md` из контрактов |
| `make mock` | Prism-мок HTTP API на :4010 |
| `make up` / `down` / `reset` / `ps` / `logs [s=...]` | Docker |
| `make db` / `make run s=<сервис>` | локальная разработка |
| `make migration s=search_service m="msg"` | миграция alembic (autogenerate) |
| `make fmt` / `lint` / `typecheck` / `test` / `check` | ruff, mypy --strict, pytest (как в CI) |
| `make smoke [URL=...]` | сквозной тест живого стенда |
| `make deploy HOST=... SSH_USER=...` | деплой (ключи API — из окружения, см. `infra/ansible/README.md`) |

## Порты и переменные

| Что | Порт | Наружу на сервере |
|---|---|---|
| frontend (nginx) | 80 | да — единственный |
| gateway / Swagger | 8000 | через nginx: `/api`, `/docs` |
| search / collector / ml | 50053 / 50054 / 50055 | нет (127.0.0.1) |
| search_db | 5435 | нет |

Переменные compose — `.env.example`; у каждого сервиса свой `services/<сервис>/.env.example`
для локального запуска. На сервере `COLLECTOR_FAKE=false` всегда.

## Отладка

- `request_id` — в заголовке `X-Request-ID` и в `error.request_id`; сервисы пишут его в лог.
- `curl localhost:8000/health/ready` — кто жив.
- gRPC напрямую (reflection включён): `grpcurl -plaintext localhost:50054 list`,
  `grpcurl -plaintext -d '{"url":"vk.com/krsk_news"}' localhost:50054 collector.v1.CollectorService/ResolveSource`.
- БД: `docker compose exec search_db psql -U search -d search`.

| Симптом | Что делать |
|---|---|
| `501 NOT_IMPLEMENTED` | сценарий ещё не написан — номер задачи в `error.message` |
| `503 SERVICE_UNAVAILABLE` | сервис не запущен: `make ps`, `make logs s=<сервис>` |
| `502 UPSTREAM_ERROR` | исключение не из `ERROR_CODES` — traceback в логах сервиса |
| ручка не видит новый RPC | забыл `make proto` (в Docker — ещё `make up`) |
| Docker Hub не качается | `"registry-mirrors": ["https://mirror.gcr.io"]` в `/etc/docker/daemon.json` |
