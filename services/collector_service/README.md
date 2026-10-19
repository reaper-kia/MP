# collector_service

Получение публикаций с площадок. Владелец — B1 (`docs/tasks/B1-collector.md`).
gRPC: `contracts/collector/v1/collector_service.proto` (справочник — `docs/GRPC.md`). Порт 50054. Своей БД нет.

```
src/collector_service/
  models.py            ← внутренние типы: Platform, Period, SourceInfo, RawPost, CollectResult, PlatformInfo
  errors.py            ← UnsupportedUrl, SourceNotFound, SourcePrivate, PlatformUnavailable, RateLimited, ...
  urls.py              ← ссылка → площадка, нормализация
  service.py           ← CollectorService: общие гарантии (период, пустые тексты, дубли, max_posts)
  connectors/
    base.py            ← Protocol PlatformConnector + NotImplementedConnector
    registry.py        ← Platform → коннектор
    vk.py ok.py max.py news.py   ← реальные коннекторы (B1-03..B1-08)
    fake.py            ← тестовые посты [FAKE], включается COLLECTOR_FAKE=true
  http.py              ← общий httpx.AsyncClient
  dependencies.py      ← сборка: настройки → коннекторы → сервис
  transport/grpc/      ← server, servicer (proto ⇄ service), mappers, errors (ERROR_CODES)
```

Новая площадка = класс в `connectors/` с методами `health / resolve / collect / search` +
строка в `dependencies.build_connectors`. Коннектор возвращает `models.*`, про proto не знает.
