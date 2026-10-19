# search_service

Ядро продукта: каталог источников, поисковые задачи, подборка, исключения, экспорт.
Владелец — B2 (`docs/tasks/B2-search.md`). gRPC: `contracts/search/v1/search_service.proto`
(справочник — `docs/GRPC.md`). Порт 50053, БД `search_db` (5435 на хосте).
Ходит в `collector_service` (50054) и `ml_service` (50055).

Слои — как в шаблоне (domain → applications → infra → transport):

```
src/search_service/
  domain/              ← enums.py (статусы, площадки, ...), value_objects.py (UtcPeriod, Красноярск),
                         exceptions.py; сущности — B2-01
  applications/
    commands/ queries/ ← по одному dataclass на каждый RPC (sources.py, searches.py, results.py)
    handlers/          ← сценарии; сейчас NotImplementedYetError с номером задачи
    ports/             ← CollectorClient, MlClient (+ их DTO), UnitOfWork
    results/           ← read models — ровно то, что уходит в proto
    exceptions.py      ← ошибки уровня приложения (+ UpstreamError от соседей)
  infra/
    clients/           ← gRPC-клиенты collector и ml: proto ⇄ DTO портов, ошибки → UpstreamError
    database/ uow/     ← SQLAlchemy; модели и репозитории — B2-01
  transport/grpc/      ← servicer (proto → команда → mediator → proto), mappers, errors
  dependencies.py      ← composition root: каналы, клиенты, UoW, регистрация хэндлеров
```

Пайплайн поиска (B2-04) запускается из хэндлера StartSearch фоновой asyncio-задачей внутри сервиса.
Внешние вызовы (collector, ml) — вне открытой транзакции UoW.
