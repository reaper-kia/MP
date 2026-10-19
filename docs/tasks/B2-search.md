# B2 — search_service (ядро: источники, поиски, подборка, экспорт)

Зона: `services/search_service/**`. Контракт: `contracts/search/v1/search_service.proto` (gRPC, порт 50053).
Модель данных и пайплайн — [ARCHITECTURE.md §3–5](../ARCHITECTURE.md). Это **самый нагруженный
сервис по критериям**: достоверность и учёт (10), архитектура и модель данных (3), сценарии 3–5.
Устройство сервиса и переменные окружения — [`services/search_service/README.md`](../../services/search_service/README.md).

**Где смотреть поля и типы:** [`docs/GRPC.md` → `search.v1`](../GRPC.md#searchv1searchservice) — твой
контракт; твои зависимости — [`collector.v1`](../GRPC.md#collectorv1collectorservice)
и [`ml.v1`](../GRPC.md#mlv1mlservice); общие — [`common.v1`](../GRPC.md#commonv1platform). Как это видит
фронт — [`docs/API.md`](../API.md): gateway мапит твои сообщения туда 1:1 (таблица — TL-03).

## Старт после pull

```bash
cd services/search_service
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q
#   23 теста, без БД и сети; tests/test_grpc.py — настоящий gRPC-сервер в процессе на фейках
```

Живой сервис (нужен Postgres на 127.0.0.1:5435 — `make db` или свой, см. README):

```bash
# офлайн, без collector и ml: посты-фикстуры и оценки-заглушки (поиск получит warning «имитация»)
DATABASE_URL=postgresql+asyncpg://search:search_local@127.0.0.1:5435/search GRPC_ADDRESS=127.0.0.1:50053 \
  COLLECTOR_MODE=stub ML_MODE=stub sh -c 'uv run alembic upgrade head && uv run search-service'
grpcurl -plaintext 127.0.0.1:50053 list          # search.v1.SearchService + health + reflection
```

С соседями и gateway — вариант Б из [README](../../README.md#быстрый-старт-после-pull), потом
`make smoke URL=http://127.0.0.1:8000` → `All good`. PowerShell — там же.

## Что изменилось при сборке `main` (прочитай, если работал в ветке `searcher`)

- Сервис снова **gRPC** по `search_service.proto` (решение владельца проекта), а не FastAPI. Отладочное
  FastAPI-приложение удалено. Твои сценарии остались как есть: `SourceHandler`, `SearchHandler`,
  `ControlHandler`, `ResultsHandler`, `ExportHandler`, `Pipeline`, `ScoringHandler`, `SaveHandler`.
  Поверх них — хэндлеры медиатора (`*QueryHandler` / `*CommandHandler`), сущность → read model —
  `applications/handlers/views.py`, ошибки домена → коды контракта — `applications/handlers/errors.py`.
  Сборка — `dependencies.py`, сервер — `transport/grpc/server.py` (health + reflection по шаблону).
- Одна `Settings` в `infra/config.py` с именами переменных из compose: `DATABASE_URL`,
  `COLLECTOR_GRPC_TARGET`, `ML_GRPC_TARGET`, `GRPC_ADDRESS`. `COLLECTOR_MODE` / `ML_MODE` по умолчанию
  `grpc`, `stub` — только явно.
- Восстановлен `pyproject.toml` (build-system, `platform-contracts`, ruff/mypy), импорты, mypy --strict.
- Миграция `migrations/versions/c5f0512fec97_init.py`: `sources`, `searches`, `search_targets`,
  `publications`, `search_results` с уникальными индексами из ARCHITECTURE §4.
- Исправлены ошибки: статусы читались строками; режим SELECTED игнорировался; JSON-тела не читались;
  миграции не видели таблиц; экспорт обрезался на 200 строках; отмена не сохраняла цели; сбор шёл по хвосту
  ссылки вместо `external_id`; повтор пересобирал все цели; неверный тип запроса в фолбэке; сохранялся
  неполный разбор запроса.
- Dockerfile по шаблону (`alembic upgrade head && search-service`) — **в Docker ещё не собирали** (B2-14).

---

### [x] B2-01 · P0 · к H+3 · домен и БД
> Сделано: `domain/entities.py` (Source, Search, SearchTarget, Publication, SearchResult с переходами
> статусов), `domain/value_objects.py` (Period по Красноярску, ≤ 366 дней), модели и репозитории в
> `infra/database/`, миграция `c5f0512fec97_init` (partial unique по `(platform, external_id) WHERE
> deleted_at IS NULL`, unique `PostKey`, unique `(search_id, publication_id)`, индекс для счётчиков).
> Миграция применяется на чистой БД (проверено на локальном Postgres); тесты переходов — `tests/test_domain.py`.

### [x] B2-02 · P0 · к H+5 · источники
> Сделано: Resolve / Create / List / Update / Delete (мягкое). Проверено через gateway: повторное
> добавление → 409 `SOURCE_ALREADY_EXISTS`, PATCH меняет только присланные поля, удалённый не виден в списке.

### [x] B2-03 · P0 · к H+6 · старт поиска и чтение
> Сделано: валидация → `SEARCH_INVALID_PARAMS` с полем в сообщении (gateway раскладывает в `details`,
> тест `test_start_search_details_field`); режимы selected (площадки — из источников) и global; ответ сразу
> `QUEUED` с целями; GetSearch / ListSearches (без целей, новые сверху).

### [x] B2-04 · P0 · к H+8 · пайплайн
> Сделано: `infra/runner.py` (asyncio-задачи по `search_id`), при старте QUEUED/RUNNING → FAILED «прерван
> перезапуском» (тест `test_interrupted_searches_marked_failed`); стадии и прогресс в БД; `Semaphore(5)`,
> 60 с на цель, ошибка цели → `mark_failed` с русским текстом (текст ошибки соседа сохраняется как есть);
> конвейер «собрали цель → сразу ScorePosts её постов»; внешние вызовы вне UoW.
> Тестов DoD на уровне пайплайна (PARTIAL при одной упавшей из трёх, COMPLETED с `total=0`) нет — B2-13.

### [x] B2-05 · P0 · к H+10 · сохранение, дедуп, период, заголовок, выдержка
> Сделано: `applications/handlers/save.py` — upsert `publications` по `PostKey`, результат в поиске один
> раз, вне периода — не сохраняется в подборку, без даты — `UNKNOWN`; заголовок или ~120 символов по
> границе слова; выдержка из `excerpt_span` с проверкой границ, иначе первые 300; `excerpt_parts` по
> подсветке. Тесты: `test_same_post_found_twice_is_one_record`, `test_unknown_date_not_marked_in_period`,
> `test_out_of_period_post_not_saved`, `test_make_title_*`. Остальные тесты из DoD — B2-13.

### [ ] B2-06 · P0 · к H+12 (стаб ML) — сделано, к H+22 (боевой) · интеграция ML
> 2026-10-19: регион в `global` (нет `region_by_source` и `region.by_content` → `IRRELEVANT` с нашим объяснением; при сбое ML — `DISPUTED`) и нарезка
> GroupPosts по 500 (`GROUP_POSTS_LIMIT`) сделаны; тесты `tests/test_scoring.py`. Не прогнано: `make check` целиком и поиск «везде» на данных.
> Сделано на стабе ML: AnalyzeQuery → `query_type` и полный разбор в `searches.query_analysis`, фразы →
> `SearchPlatform.queries`, ML недоступен → фразы `[query]` и warning, `degraded` → warning «ML работал в
> упрощённом режиме»; ScorePosts батчами по 30, ≤ 3 параллельно, 60 с, упавший батч → `DISPUTED` «Не удалось
> проверить автоматически — проверьте вручную»; GroupPosts по прошедшим отбор, `group_id` с префиксом поиска.

**Осталось.**
1. **Боевой прогон**, когда ML-03…ML-05 отдадут `degraded=false`: warning пропал, объяснения осмысленные,
   спорных не 100 %, время ScorePosts укладывается в 60 с на батч 30 постов (если нет — уменьшить батч).

**Контракт** ([ml.v1](../GRPC.md#mlv1mlservice)) — для справки:
```
ml.ScorePosts({context, query, analysis, posts: PostForScoring[]}) -> {scores: PostScore[], degraded}
  PostForScoring { id = search_results.id, optional title, text, source_name, source_is_regional }
  PostScore      { id, relevance, score 0..1, explanation, region {by_content, evidence}, sentiment,
                   excerpt_span {start, end}, highlight_spans[] }  # индексы Python-строки text, end не включ.
ml.GroupPosts({context, posts: [{id, optional title, text}]}) -> {groups: [{group_id, post_ids[], representative_post_id}]}
```

### [ ] B2-07 · P0 · к H+10 · выдача
> 2026-10-19: `matched` считается после оценки и после `SetExcluded` (исключённые не считаются — решение владельца): `recount_matched`,
> `TargetRepo.set_matched`. Тесты `test_matched_*` (в т.ч. «3 поста, один IRRELEVANT → 2»).
> Сделано: ListResults (фильтры relevance / platforms / target_ids / date_status / include_excluded,
> сортировки, `total`, `has_more`), ListGroups с полным списком размещений, `SearchCounts`. Проверено через
> gateway: вкладки, группы, исключение пересчитывает счётчики.

**Осталось.** Посмотреть «в подборке N» на Postgres через gateway (`make smoke` + блок «Где искали»).

**DoD.** Тест: цель с 3 постами, один `IRRELEVANT` → `matched == 2`.

### [ ] B2-08 · P0 · к H+12 · экспорт XLSX
> 2026-10-19: п. 1–3 сделаны — слова вместо кодов («ВКонтакте», «Готово», «позитивная»), «Сформировано» и даты публикаций по Красноярску,
> тест `tests/test_export.py` (число строк и порядок ссылок = ListResults); сюжеты нумеруются 1…N.
> Сделано: `applications/handlers/export.py` — строки тем же запросом, что ListResults (без лимита), лист
> «Подборка» с шапкой (запрос, как понят, период, режим, площадки, сформировано, «Публикаций в подборке: N
> (из них без даты: K; исключено вручную: M)»), таблица из 13 колонок, ссылка на публикацию — гиперссылкой,
> автофильтр, закреплённая шапка, ширины; лист «Охват». Smoke проверяет: строк со ссылками = `counts.total`.

**Осталось.**
1. Внешний вид — согласовать с дизайнером (UI-07).

Имя файла ASCII: `podborka_<period_to>_<id8>.xlsx`. DOCX — в B2-10.

### [x] B2-09 · P0 · к H+18 · исключение, повтор, отмена
> Сделано: SetExcluded пачкой → пересчитанные `counts` (`RESULT_NOT_FOUND` на чужой id); RetrySearch —
> только FAILED (или указанные) цели, `attempts += 1`, `SEARCH_NOT_FINISHED`, пока идёт; CancelSearch —
> незавершённые цели → `SKIPPED` и сохраняются. Тесты `test_retry_only_failed_targets`,
> `test_cancel_running_search`; проверено через gateway.

### [ ] B2-13 · P0 · к H+20 · тесты из DoD, которых нет
> 2026-10-19: тесты написаны — `tests/test_rules.py` (названия по ТЗ, PARTIAL / `total=0` / FAILED на фейках), `test_export.py`, `test_scoring.py`.
> Осталось: `uv run pytest -q` целиком и зелёный CI (в этой среде `tests/test_grpc.py` не запускался).
Названия — по ТЗ, чтобы на защите показать «вот проверка правила»:
1. `test_same_text_in_three_groups_is_three_records` — одинаковый текст в трёх группах = три публикации.
2. `test_excerpt_is_substring_of_original` — `excerpt` всегда подстрока `publications.text`.
3. `test_retry_does_not_duplicate` — повтор цели с теми же постами не добавляет строк в подборку.
4. Пайплайн на фейках: 3 цели, одна падает → `PARTIAL`, посты двух других сохранены; все пустые →
   `COMPLETED`, `total=0`.
5. XLSX: строки и порядок ссылок = ListResults (B2-08 п. 1); `matched` (B2-07).

**DoD.** Все в `uv run pytest -q`, CI зелёный.

### [ ] B2-14 · P0 · вместе с TL-11 · сервис в Docker
> 2026-10-19: образ собирается, `docker compose up` поднимает стенд, миграции при старте проходят, `make smoke` → All good
> (`COLLECTOR_FAKE=true`). Осталось: прогон на сервере (TL-11) и с реальными ключами.
Dockerfile не собирали. Вместе с TL: `make reset && make up`, в `make logs s=search_service` —
`alembic upgrade head` прошёл на пустой `search_db`, сервер слушает 50053; `make smoke` → `All good`.
Если миграция падает на старте контейнера — поиск по `DATABASE_URL` в compose (`search_db:5432`).

### [ ] B2-12 · P1 · к H+24 · `request_id` до соседей и в логах
> 2026-10-19: сделано — `request_id` входящего запроса хранится в ContextVar (`applications/request_context.py`), попадает в логи и в
> `context_to_proto()`; фоновый пайплайн наследует его от `StartSearch` / `RetrySearch`. Тест `test_request_id.py`. Осталось: проверить
> по логам трёх сервисов на живом стенде.
Сейчас `infra/clients/*` вызывают `context_to_proto()` без `request_id`, поэтому цепочку gateway → search →
collector / ml по логам не связать (общий DoD п. 5). Сделать: брать `request_id` из входящего
`RequestContext`; для пайплайна (фоновая задача) — запомнить `request_id` запроса `StartSearch` /
`RetrySearch` и передавать его в каждый вызов collector и ml и в `structlog`-контекст.

**DoD.** Один поиск в логах трёх сервисов находится по одному `request_id`.

### [ ] B2-10 · P2 · к H+32 · импорт XLSX и DOCX
> 2026-10-19: сделано — `ImportSources` (`source_import.py`, отчёт created / duplicates / failed с номером строки; строки по очереди, до 500) и
> `ExportSearch(DOCX)` (`docx_writer.py` без python-docx: зависимости и `uv.lock` не менялись). Тесты `test_import.py`, `test_export.py`,
> `test_grpc.py`. Осталось: прогнать через gateway, проверить внешний вид DOCX с дизайнером.
Сейчас оба отвечают `UNIMPLEMENTED` (gateway → 501): `ImportSourcesCommandHandler` и `ExportSearchQueryHandler`
для `format=DOCX` (в сообщении 501 указан номер задачи B2-10).
**Контракт:** `ImportSourcesRequest {context, xlsx: bytes}` → `ImportSourcesResponse {created: uint32,
duplicates: uint32, failed: [{row: uint32 (номер строки Excel, с 1), value: str, error: {code, message}}]}`.
`ImportSources`: строки → `SourceHandler` создания по одной, отчёт created/duplicates/failed с номером строки.
`ExportSearch(format=DOCX)` (`python-docx`): шапка как в XLSX + список публикаций (заголовок-ссылка,
источник, дата, выдержка). Gateway уже передаёт файл и отдаёт ответ — менять его не нужно.

### [ ] B2-11 · P1 · к H+36 · метрики для презентации
> 2026-10-19: длительность стадий (`analyzing_query`, `collecting`, `scoring`, `grouping`, `total`) и каждой цели (`target_collect`, `target_scoring`)
> пишется в лог строкой `search stage finished`. Осталось: цифры на 30 источниках **реального VK** (после B1-03).
Логировать длительность каждой стадии (`analyzing_query`, `collecting`, `scoring`, `grouping`) и всего
поиска с `search_id` (отдельное поле в контракте не нужно — есть `started_at` / `finished_at`). Дать TL
цифры: среднее время поиска на 30 источниках — **на реальном VK** (после B1-03), на тестовых данных цифра
ничего не значит.

---

## Интеграция: от кого ты зависишь

| Что | От кого | Что делаешь ты |
|---|---|---|
| Реальные посты VK | TL-04 (ключ) → B1-03 | прогон с `COLLECTOR_FAKE=false`: 60 с на цель хватает для `wall.get` за 14 дней? `max_posts` 300/500 не режет нужное? |
| OK / MAX | B1-04 / B1-05 | ничего: их ошибки 501 уже честно ложатся в цели как «не удалось» |
| Настоящий отбор | ML-03…ML-06 | B2-06 «Осталось» п. 3 |
| Каталог для «везде» | TL-06 | ничего — источники идут через CreateSource |
| Экран «Где искали» | FE-04 | `matched` (B2-07), русские тексты ошибок целей |
