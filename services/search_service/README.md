# search_service

Ядро продукта: каталог источников, поисковые задачи, подборка, исключения, экспорт.
Владелец — B2 (`docs/tasks/B2-search.md`). gRPC: `contracts/search/v1/search_service.proto`
(справочник — `docs/GRPC.md`). Порт 50053, БД `search_db` (5435 на хосте).
Ходит в `collector_service` (50054) и `ml_service` (50055).

Слои — как в шаблоне (domain → applications → infra → transport):

```
src/search_service/
  domain/              ← entities.py (Source, Search, SearchTarget, Publication, SearchResult),
                         enums.py, value_objects.py (Period по Красноярску), errors.py
  applications/
    commands/ queries/ ← по одному dataclass на каждый RPC (sources.py, searches.py, results.py)
    handlers/          ← сценарии B2 (SourceHandler, SearchHandler, ControlHandler,
                         ResultsHandler, ExportHandler, Pipeline, Scoring, Save) и поверх них
                         хэндлеры медиатора *QueryHandler / *CommandHandler;
                         views.py — сущность → read model, errors.py — ошибки домена → приложения
    ports/             ← collector_client.py, ml_client.py (+ DTO), uow.py, repositories.py, runner.py
    results/           ← read models — ровно то, что уходит в proto
    exceptions.py      ← ошибки уровня приложения (+ UpstreamError от соседей)
  infra/
    clients/           ← gRPC-клиенты collector и ml: proto ⇄ DTO портов, ошибки → UpstreamError
    collector_stub.py, ml_client.py ← заглушки соседей для офлайн-разработки (COLLECTOR_MODE/ML_MODE=stub)
    database/          ← SQLAlchemy: модели, репозитории, UnitOfWork (сессия на каждый `async with`)
    runner.py          ← фоновые asyncio-задачи пайплайна по search_id
    config.py          ← Settings (переменные окружения ниже)
  transport/grpc/      ← servicer (proto → команда → mediator → proto), mappers, errors
  dependencies.py      ← composition root: БД, клиенты, пайплайн, регистрация хэндлеров
```

Пайплайн поиска (B2-04) запускается из StartSearch фоновой asyncio-задачей внутри сервиса:
analyzing_query → collecting (цели параллельно, сразу скоринг) → scoring → grouping → done.
На старте сервиса поиски в статусе QUEUED/RUNNING помечаются FAILED («прерван перезапуском»).

## Переменные окружения

| Переменная | По умолчанию | |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://search:search_local@localhost:5435/search` | |
| `GRPC_ADDRESS` | `[::]:50053` | |
| `COLLECTOR_GRPC_TARGET` | `localhost:50054` | |
| `ML_GRPC_TARGET` | `localhost:50055` | |
| `COLLECTOR_MODE` | `grpc` | `stub` — посты-фикстуры без collector_service (поиск получает warning) |
| `ML_MODE` | `grpc` | `stub` — оценки-заглушки без ml_service |
| `STUB_FAIL_PLATFORMS` | пусто | `ok,max` — какие площадки стаб коллектора «роняет» |

## Запуск

```bash
make db                         # Postgres в Docker (или свой на 5435)
make run s=search_service       # alembic upgrade head && search-service
```

Миграции: `migrations/versions/`; новая — `make migration s=search_service m="..."`.
В Docker (`services/search_service/Dockerfile`) — тоже сначала `alembic upgrade head`, потом сервер.

Импорт источников из XLSX (`ImportSources`, колонки A — ссылка, B — название, C — «региональный»)
и выгрузка DOCX (`ExportSearch format=DOCX`) работают. DOCX собирается без python-docx
(`applications/handlers/docx_writer.py`), чтобы не менять зависимости и `uv.lock`.

Логи: `request_id` из gateway добавляется ко всем строкам лога запроса и уходит в collector и ml
(в том числе из фонового пайплайна). Длительность стадий поиска — строки `search stage finished`
(`stage` = `analyzing_query | collecting | scoring | grouping | total`, а также `target_collect` и
`target_scoring` по каждой цели; сбор и оценка цели идут конвейером, поэтому `collecting` включает
оценку).
