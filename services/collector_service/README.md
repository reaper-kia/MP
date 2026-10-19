# collector_service

Получение публикаций с площадок. Владелец — B1 (`docs/tasks/B1-collector.md`).
gRPC: `contracts/collector/v1/collector_service.proto` (справочник — `docs/GRPC.md`). Порт 50054. Своей БД нет.

Слои — как в `search_service` (Mediator, CQRS), но без UnitOfWork и Postgres: сервис только читает
с площадок, команд, которые меняют состояние, в нём нет — все четыре запроса это Query.

```
src/collector_service/
  domain/
    enums.py           ← Platform, Health
    value_objects.py   ← Period, PlatformInfo, SourceInfo, RawPost, PostMetrics, CollectResult
    exceptions.py      ← UnsupportedUrl, SourceNotFound, SourcePrivate, PlatformUnavailable, RateLimited
    urls.py            ← ссылка → нормализованная форма, хост, части пути
    services.py        ← finalize_result: общие гарантии (период, дубли, пустой текст, max_posts)
  applications/
    mediator.py        ← Mediator + маркер Command[T] (копия из search_service)
    queries/           ← GetPlatforms, ResolveSource, CollectFromSource, SearchPlatform
    handlers/          ← по одному хэндлеру на запрос
    ports/connectors.py← PlatformConnector и ConnectorRegistry (протоколы)
    exceptions.py      ← InvalidRequest, NotImplementedYet; limits.py, context.py
  infra/
    config.py http.py  ← настройки и общий httpx.AsyncClient
    connectors/        ← vk.py (готов) ok.py max.py news.py (B1-04..B1-08), fake.py, registry.py, base.py
    vk_api/            ← клиент VK API: client.py (ретраи, коды ошибок), limiter.py, transport.py, mapping.py
  transport/grpc/      ← servicer (proto → Query → mediator → proto), mappers, errors (ERROR_CODES), server
  dependencies.py      ← composition root: настройки → коннекторы → реестр → хэндлеры в Mediator
```

Зависимости идут только вниз: `domain ← applications ← infra / transport`. Это проверяет
`tests/test_layering.py`.

Новая площадка = класс в `infra/connectors/` с методами `health / resolve / collect / search` +
строка в `dependencies.build_connectors`. Коннектор возвращает типы из `domain/`, про proto не знает.
Новый RPC = Query в `applications/queries/` + хэндлер в `applications/handlers/` + регистрация в
`dependencies.build_mediator` + метод в servicer (тест `test_every_query_has_a_handler` ловит
забытую регистрацию).

## ВКонтакте (B1-03, health — часть B1-07)

Нужен сервисный ключ: `VK_SERVICE_TOKEN` в `.env`. Без него `GetPlatforms` честно отвечает
`UNAVAILABLE: Не настроен доступ`, остальные вызовы — `PLATFORM_UNAVAILABLE`.

| Режим | Как получаем |
|---|---|
| `ResolveSource` | `groups.getById` для `vk.com/имя`, `club123`, `public123`, `event123`, `vk.ru`, `m.vk.com`. Страница человека (`vk.com/id1`) — `UNSUPPORTED_URL` |
| `CollectFromSource` | `wall.get` по 100 постов, пока посты не станут старше начала периода; закреплённый старый пост на это не влияет |
| `SearchPlatform` | `newsfeed.search` по каждой фразе (до 200 за страницу, VK отдаёт не больше ~1000 на фразу), дубли между фразами схлопываются |

- Текст репоста = свой текст + `\n\n` + текст оригинала; посты без текста пропускаются и считаются в `warnings`.
- Метрика, которой нет в ответе VK, остаётся пустой (не 0); дата — только из `date`.
- Коннектор **не** сужает по региону и **не** фильтрует по `keywords`: фразы приходят от ML как есть,
  ищем по всему открытому VK. Привязка к региону и отбор по смыслу — ML и `search_service`.
- Лимит ≈3 запроса/с (`VK_REQUESTS_PER_SECOND`), ретраи с паузой на ошибки VK 6 и 10, до 4 попыток.
  Ошибки VK: 5 → `PLATFORM_UNAVAILABLE`, 15/18/30 → `SOURCE_PRIVATE`, 100/113 → `SOURCE_NOT_FOUND`,
  6/9/29 после ретраев → `RATE_LIMITED`. Токен передаётся в теле POST и в логи не попадает.
- Health: запрос `users.get` с ключом, «здорова» кэшируется на 5 минут, проблема — на 1 минуту.

### Fixtures и сверка с живым VK

`tests/fixtures/vk/*.json` — **синтетические** (составлены по документации VK, подписаны ключом
`_synthetic`). Они проверяют нашу логику, но не то, что VK отвечает именно так. Настоящие ответы:

```
VK_SERVICE_TOKEN=... python scripts/record_vk_fixtures.py krsk_news "ДТП Красноярск"
pytest tests/test_vk_real_fixtures.py
```

Скрипт кладёт ответы в `tests/fixtures/vk/real/` (без токена); пока их нет, этот тест пропускается.
