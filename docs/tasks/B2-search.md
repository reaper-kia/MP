# B2 — search_service (ядро: источники, поиски, подборка, экспорт)

Зона: `services/search_service/**`. Контракт: `contracts/search/v1/search_service.proto`.
Каркас уже есть (TL-01): все 15 RPC проведены servicer → mediator → хэндлер, хэндлеры бросают
`NotImplementedYetError` с номером задачи — заменяешь их тела. Готово: команды/запросы, read models,
мапперы proto, порты и gRPC-клиенты collector/ml (`applications/ports/`, `infra/clients/`), фейки
(`tests/fakes.py`), `UtcPeriod.from_local_dates`. Стиль шаблона:
domain → applications (commands/queries/handlers/ports) → infra → transport.
Модель данных и пайплайн — [ARCHITECTURE.md §3–5](../ARCHITECTURE.md). Это **самый нагруженный
сервис по критериям**: достоверность и учёт (10), архитектура и модель данных (3), сценарии 3–5.

**Где смотреть поля и типы:** [`docs/GRPC.md` → `search.v1`](../GRPC.md#searchv1searchservice) — твой
контракт (сообщения с типами и комментариями); твои зависимости — [`collector.v1`](../GRPC.md#collectorv1collectorservice)
и [`ml.v1`](../GRPC.md#mlv1mlservice); общие — [`common.v1`](../GRPC.md#commonv1platform). Как это видит
фронт (семантика полей, примеры) — [`docs/API.md`](../API.md): gateway мапит твои сообщения туда 1:1
(таблица маппинга — TL-03). В задачах ниже нужные поля выписаны прямо в тексте.

Порты (Protocol) в `applications/ports/`: `CollectorClient`, `MlClient`, `UnitOfWork` (+ репозитории
sources, searches, targets, publications, results). Фейки коллектора и ML — в `tests/fakes.py`,
все хэндлеры тестируются без сети и БД.

---

### [ ] B2-01 · P0 · к H+3 · домен и БД
**Сделать.**
1. Сущности: `Source`, `Search`, `SearchTarget`, `Publication`, `SearchResult`. Value objects:
   `Platform`, `Period` (даты YYYY-MM-DD → UTC-границы по `Asia/Krasnoyarsk`, from ≤ to, не больше
   366 дней), `PostKey(platform, source_external_id, post_external_id)`.
2. Переходы статусов — методы сущностей: `Search.start()`, `.finish()` (сам решает completed/partial/
   failed по целям), `.cancel()`; `SearchTarget.mark_done(fetched)`, `.mark_empty()`, `.mark_failed(err)`.
   Нельзя `finish` с незавершёнными целями → доменная ошибка.
3. Модели SQLAlchemy и миграция по схеме из ARCHITECTURE §4 (уникальные индексы обязательно).

**Таблицы и типы колонок** (Postgres; enum'ы — `String(32)` с проверкой в домене, проще миграций):

| Таблица | Колонка | Тип | Null | Примечание |
|---|---|---|---|---|
| `sources` | `id` | uuid PK | | |
| | `platform` | varchar(16) | | `vk\|ok\|max\|news` |
| | `external_id`, `screen_name`, `url`, `name` | text | | из `collector.SourceInfo` |
| | `city` | text | да | |
| | `is_regional`, `is_active` | bool | | default `true`, `true` |
| | `notes` | text | | default `''` |
| | `deleted_at` | timestamptz | да | мягкое удаление |
| | `created_at`, `updated_at` | timestamptz | | |
| | **UNIQUE** `(platform, external_id) WHERE deleted_at IS NULL` | | | partial index |
| `searches` | `id` | uuid PK | | |
| | `query` | text | | |
| | `query_type` | varchar(16) | да | заполняется после AnalyzeQuery |
| | `period_from`, `period_to` | date | | как ввёл пользователь |
| | `mode` | varchar(16) | | `selected\|global` |
| | `platforms` | varchar[] | | |
| | `source_ids` | uuid[] | | |
| | `query_analysis` | jsonb | да | полный `ports.ml.QueryAnalysis` (нужен ScorePosts); наружу — `QueryAnalysisView` |
| | `status`, `stage` | varchar(24) | | |
| | `warnings` | jsonb | | `[]` |
| | `created_at` / `started_at` / `finished_at` | timestamptz | / да / да | |
| `search_targets` | `id` uuid PK, `search_id` uuid FK, `kind` varchar, `platform` varchar | | | |
| | `source_id` | uuid | да | FK sources (может быть удалён позже) |
| | `name`, `url` | text / text null | | **снимок** на момент запуска |
| | `status` varchar, `fetched` int, `matched` int, `attempts` int | | | |
| | `error_code`, `error_message` | text | да | |
| | `started_at`, `finished_at` | timestamptz | да | |
| `publications` | `id` uuid PK | | | |
| | `platform`, `source_external_id`, `post_external_id` | text | | **UNIQUE** вместе |
| | `url`, `source_name`, `source_url`, `text` | text | | из `RawPost` |
| | `title` | text | да | |
| | `published_at` | timestamptz | да | |
| | `metrics` | jsonb | | `{"views": 5400, "likes": null, ...}` |
| | `is_repost` bool, `repost_of_url` text null | | | |
| | `first_seen_at`, `last_seen_at` | timestamptz | | |
| `search_results` | `id` uuid PK, `search_id` FK, `publication_id` FK, `target_id` FK | | | **UNIQUE** `(search_id, publication_id)` |
| | `relevance` | varchar(16) | да | `null` = ещё не оценено ML → в выдачу и счётчики не попадает |
| | `score` | real | да | |
| | `explanation` | text | | `''` |
| | `region_by_source`, `region_by_content` | bool | | |
| | `region_evidence` | text | | `''` |
| | `sentiment` | varchar(16) | да | |
| | `excerpt_start`, `excerpt_end` | int | да | позиции в `publications.text` |
| | `highlights` | jsonb | | `[[start,end], ...]` |
| | `group_id` | text | да | |
| | `date_status` | varchar(16) | | `in_period\|unknown` |
| | `excluded` bool default false, `excluded_at` timestamptz null | | | |
| | индекс `(search_id, relevance, excluded)` | | | для счётчиков |

**DoD.** Миграция применяется на чистой БД; тесты на переходы статусов.

### [ ] B2-02 · P0 · к H+5 · источники
**Контракт** ([search.v1 — источники](../GRPC.md#searchv1source)):

| RPC | Запрос | Ответ | Ошибки |
|---|---|---|---|
| `ResolveSource` | `{context, url}` | `{preview: SourcePreview}` | проброс `UNSUPPORTED_URL`, `SOURCE_NOT_FOUND`, `SOURCE_PRIVATE`, `PLATFORM_UNAVAILABLE` из collector |
| `CreateSource` | `{context, url, optional name, is_regional: bool, notes}` | `{source: Source}` | + `SOURCE_ALREADY_EXISTS` |
| `ListSources` | `{context, platforms: Platform[], q, optional is_active, limit (0→50, ≤200), offset}` | `{sources: Source[], total: uint32, has_more}` | |
| `UpdateSource` | `{context, source_id, optional name, optional is_regional, optional is_active, optional notes}` | `{source}` | `SOURCE_NOT_FOUND` |
| `DeleteSource` | `{context, source_id}` | `{}` | `SOURCE_NOT_FOUND` |

```
Source        { id, platform, external_id, url, name, optional city, is_regional, is_active, notes,
                created_at: Timestamp, updated_at: Timestamp }
SourcePreview { platform, external_id, url, name, optional city, optional members_count: int64,
                optional existing_source_id }
```
`collector.ResolveSource` → `SourceInfo {platform, external_id, screen_name, url, name, city?,
members_count?, is_closed}`; `is_closed=true` → `SOURCE_PRIVATE`. В `UpdateSource` менять только поля, у
которых `request.HasField(...)`.

`ResolveSource` (→ `collector.ResolveSource` + проверка, есть ли в каталоге), `CreateSource`
(резолв, имя с площадки если не задано, `SOURCE_ALREADY_EXISTS`), `ListSources` (фильтры, поиск по
name/url `ILIKE`, `total`), `UpdateSource`, `DeleteSource` (мягкое — `deleted_at`).

**DoD.** Добавить `vk.com/krsk_news` дважды → второй раз 409; удалить → в списке нет, в старых поисках
имя осталось.

### [ ] B2-03 · P0 · к H+6 · старт поиска и чтение
`StartSearch`: валидация (`SEARCH_INVALID_PARAMS`: пустой/короче 3 символов запрос, from > to,
`selected` без источников, источник другой площадки, чем выбранные), создание `Search` + целей
(снимок имени/ссылки), запуск пайплайна в фоне, ответ сразу со `status=QUEUED`.
`GetSearch` (с целями, счётчиками, прогрессом), `ListSearches` (без целей, новые сверху).

**Контракт** ([search.v1.Search](../GRPC.md#searchv1search)):
```
StartSearchRequest { context, query: str, period_from: "YYYY-MM-DD", period_to: "YYYY-MM-DD",
                     mode: SearchMode (SELECTED|GLOBAL), platforms: Platform[], source_ids: str[] }
  -> { search: Search }                           # status=QUEUED, targets уже созданы (PENDING)
GetSearchRequest   { context, search_id }       -> { search: Search }            # SEARCH_NOT_FOUND
ListSearchesRequest{ context, limit, offset }   -> { searches: Search[] (без targets), has_more }

Search { id, status: SearchStatus, stage: SearchStage, progress: SearchProgress, params: SearchParams,
         optional query_analysis: QueryAnalysisView, targets: SearchTarget[], counts: SearchCounts,
         warnings: str[], created_at, optional started_at, optional finished_at }
SearchParams { query, query_type, period_from, period_to, mode, platforms, source_ids }
QueryAnalysisView { query_type, summary, search_queries[], needs_clarification, clarification_hint }
```
Ошибки валидации — `SEARCH_INVALID_PARAMS` (`INVALID_ARGUMENT`); поле — в сообщении:
`"period_from: должна быть не позже period_to"` (gateway разложит в `details[{field, message}]`).

### [ ] B2-04 · P0 · к H+8 · пайплайн
**Цель.** Сердце продукта. Устойчиво, параллельно, с честными статусами.

**Сделать.**
1. `SearchRunner` (infra): реестр `asyncio.Task` по `search_id`, запуск/отмена; при старте сервиса
   все `RUNNING/QUEUED` → `FAILED` с warning «Поиск прерван перезапуском сервиса».
2. Стадии по ARCHITECTURE §3: analyzing_query → collecting → scoring → grouping → done; `stage`
   и прогресс пишутся в БД после каждой цели (фронт опрашивает).
3. Сбор: `asyncio.Semaphore(5)`, таймаут на цель (60 с), ошибка цели → `mark_failed(code, message)`
   с **русским** сообщением для пользователя («Одноклассники не ответили за 60 секунд»), поиск идёт дальше.
4. Каждая цель после сбора сразу сохраняет посты (B2-05) и **сразу** отправляет свои новые посты в
   `ScorePosts` (конвейер: собрали цель → оценили её посты) — так подборка растёт во время поиска, а
   найденное сохраняется при падении остальных. `stage=collecting`, пока идёт хоть одна цель; потом
   `scoring` (доделать хвост батчей) → `grouping` (по всем прошедшим отбор).

**Контракт — вызовы соседей** ([collector.v1](../GRPC.md#collectorv1collectorservice)):
```
collector.CollectFromSource({context, platform, source_external_id, period: {start, end}, keywords, max_posts: 300})
    -> {posts: RawPost[], truncated, warnings}      # truncated → warning «… обрезано до 300 постов»
collector.SearchPlatform({context, platform, queries: analysis.search_queries, period,
                          region_terms: ["Красноярск", "Красноярский край", ...], max_posts: 500})
    -> {posts: RawPost[], truncated, warnings}
```
Ошибка вызова (gRPC status + `error-code`) → `target.mark_failed(code, message_ru)`; таймаут клиента
(`DEADLINE_EXCEEDED`) → `TIMEOUT`. Тексты для `message_ru` — по коду: `PLATFORM_UNAVAILABLE` «{Площадка}
недоступна», `TIMEOUT` «{Площадка} не ответила за 60 секунд», `SOURCE_NOT_FOUND` «Источник не найден на
площадке», `SOURCE_PRIVATE` «Группа закрыта», `RATE_LIMITED` «Превышен лимит запросов к площадке».

**Что пишется в `SearchTarget`** ([search.v1.SearchTarget](../GRPC.md#searchv1searchtarget)): `status`
(`PENDING→RUNNING→DONE|EMPTY|FAILED|SKIPPED`), `fetched` = `len(posts в периоде)`, `matched` = сколько
из них `direct|indirect|disputed`, `error {code, message}`, `attempts`, `finished_at`.
`SearchProgress {targets_total, targets_finished (DONE+EMPTY+FAILED+SKIPPED), percent}` — `percent`:
collecting = 10 + 70·finished/total, scoring 80–90, grouping 90–99, done 100.
5. Короткие транзакции: внешние вызовы (collector, ml) **вне** открытого UoW.

**DoD (тесты на фейках).** 3 цели, одна падает → `PARTIAL`, посты двух других сохранены;
все падают → `FAILED`; 0 постов везде → `COMPLETED`, `total=0`; отмена → `CANCELLED`.

### [ ] B2-05 · P0 · к H+10 · сохранение, дедуп, период, заголовок, выдержка
**Цель.** Критерий «Достоверность и учёт» (10 баллов) живёт здесь.

**Контракт: `RawPost` → таблицы → `Result`** ([RawPost](../GRPC.md#collectorv1rawpost),
[Result](../GRPC.md#searchv1result)):

| `Result` (выдача) | откуда |
|---|---|
| `id` | `search_results.id` |
| `publication_id` | `publications.id` |
| `platform` | `RawPost.platform` |
| `source {source_id?, name, url, is_regional}` | каталог по `(platform, source_external_id)`, иначе `RawPost.source_name/source_url`, `is_regional=false`, `source_id` не задан |
| `url` | `RawPost.url` (как есть — collector уже канонизировал) |
| `title`, `title_source` | `RawPost.title` → `TITLE`; иначе начало `text` → `POST_START` (п. 4) |
| `excerpt`, `excerpt_parts[{text, highlight}]` | `text[excerpt_start:excerpt_end]`, нарезка по `highlights` (п. 5) |
| `published_at?`, `date_status` | `RawPost.published_at` (если `HasField`), `IN_PERIOD`/`UNKNOWN` |
| `relevance`, `score`, `explanation`, `sentiment` | `ml.PostScore` (B2-06) |
| `region {by_source, by_content, evidence}` | `source.is_regional` / `PostScore.region` |
| `group_id?`, `group_size` | `ml.GroupPosts` / `COUNT(*)` по group_id в этом поиске |
| `metrics {views?, likes?, reposts?, comments?}` | `RawPost.metrics` (jsonb, `null` сохраняется) |
| `excluded` | `search_results.excluded` |
| `found_by_target_id` | `search_results.target_id` |

**Сделать.**
1. Upsert `publications` по `PostKey` (`INSERT … ON CONFLICT DO UPDATE` текст/метрики/`last_seen_at`).
2. `search_results` — `ON CONFLICT (search_id, publication_id) DO NOTHING`; `target_id` = первая нашедшая цель.
3. Период: в периоде → `IN_PERIOD`; вне → не добавлять; нет даты → `UNKNOWN`.
4. Заголовок: `RawPost.title` → `TITLE`; иначе первые ~120 символов по границе слова + «…» → `POST_START`.
5. Выдержка: из `excerpt_span` ML; проверить, что span внутри текста; нет span — первые 300 символов.
   `excerpt_parts` — нарезка по `highlight_spans`, пересечённым с выдержкой. **Текст не меняем**
   (только схлопнуть пробелы/переводы строк для показа).
6. `region_by_source` = `source.is_regional` (для найденных глобально и не в каталоге — false).

**DoD (тесты, назвать по ТЗ).** `test_same_post_found_twice_is_one_record`,
`test_same_text_in_three_groups_is_three_records`, `test_unknown_date_not_marked_in_period`,
`test_excerpt_is_substring_of_original`, `test_retry_does_not_duplicate`.

### [ ] B2-06 · P0 · к H+12 (стаб ML), H+22 (боевой) · интеграция ML
**Контракт** ([ml.v1](../GRPC.md#mlv1mlservice)):
```
ml.AnalyzeQuery({context, query}) -> {analysis: QueryAnalysis, degraded: bool}
  QueryAnalysis { query_type, summary, search_queries[], entities[{text, type}], must_concepts[],
                  exclude_concepts[], needs_clarification, clarification_hint }
  → searches.query_type, searches.query_analysis (jsonb: QueryAnalysisView), фразы → SearchPlatform.queries

ml.ScorePosts({context, query, analysis, posts: PostForScoring[]}) -> {scores: PostScore[], degraded}
  PostForScoring { id = search_results.id, optional title, text = publications.text,
                   source_name, source_is_regional }
  PostScore      { id, relevance (DIRECT|INDIRECT|DISPUTED|IRRELEVANT), score: float 0..1, explanation,
                   region {by_content, evidence}, sentiment, excerpt_span {start, end},
                   highlight_spans[{start, end}] }      # позиции — индексы Python-строки text, end не включ.
  → search_results.relevance/score/explanation/region_by_content/region_evidence/sentiment/
    excerpt_start/excerpt_end/highlights
  проверка: len(scores) == len(posts), id совпадают; 0 <= start < end <= len(text), иначе span игнорировать

ml.GroupPosts({context, posts: [{id, optional title, text}]}) -> {groups: [{group_id, post_ids[], representative_post_id}]}
  → search_results.group_id (сохранять как f"{search_id[:8]}-{group_id}", чтобы не путать поиски)
```

`AnalyzeQuery` → `query_type`, `query_analysis`, фразы для `SearchPlatform`; ML недоступен →
фразы = `[query]` и warning. `ScorePosts` батчами по 30, параллельно ≤ 3 батча; таймаут 60 с;
упал батч → эти посты `DISPUTED` с explanation «Не удалось проверить автоматически — проверьте вручную»
(не теряем, не выдумываем). `GroupPosts` — по прошедшим отбор; упал → без групп.
Регион в `global`: `irrelevant`, если нет ни `by_source`, ни `by_content` (объяснение — от нас).

### [ ] B2-07 · P0 · к H+10 · выдача
**Контракт** ([ListResults](../GRPC.md#searchv1listresultsrequest), [ResultFilter](../GRPC.md#searchv1resultfilter)):
```
ListResultsRequest { context, search_id, filter: ResultFilter, sort: ResultSort, limit (0→50, ≤200), offset }
  -> { results: Result[], total: uint32 (по фильтру, без limit), has_more }
ListGroupsRequest  { context, search_id, filter, limit, offset }
  -> { groups: ResultGroup[], total, has_more }
ResultFilter { relevance: Relevance[] (пусто = DIRECT+INDIRECT+DISPUTED), platforms: Platform[],
               target_ids: str[], date_status: DateStatus[] (пусто = любые), include_excluded: bool }
ResultSort   RELEVANCE (по умолч.: DIRECT→INDIRECT→DISPUTED, внутри score desc, потом published_at desc NULLS LAST)
             | DATE_DESC | DATE_ASC  (NULLS LAST в обоих)
ResultGroup  { group_id, title (у representative), size, platforms[], earliest_published_at?, results: Result[] (ВСЕ) }
SearchCounts { total, direct, indirect, disputed, rejected, excluded, unknown_date, groups }
```
Вне фильтра всегда: `relevance IS NULL` (не оценено) не показывается.
Счётчики (одним запросом по `search_results` поиска):
`direct/indirect/disputed` — `NOT excluded`; `total = direct+indirect+disputed`; `rejected` — `IRRELEVANT`;
`excluded` — `excluded AND relevance <> IRRELEVANT`; `unknown_date` — из total с `UNKNOWN`;
`groups` — `COUNT(DISTINCT group_id)` из total (одиночки — свой group_id).

`ListResults`: фильтры `relevance` (по умолчанию direct+indirect+disputed), `platforms`, `target_ids`,
`date_status`, `include_excluded`; сортировки; `total`, `has_more`. `ListGroups`: группы с **полным**
списком размещений. Счётчики `SearchCounts` — одним SQL с `COUNT(*) FILTER (WHERE …)`.
`matched` у цели = сколько её постов в подборке.

### [ ] B2-08 · P0 · к H+12 · экспорт XLSX
**Цель.** Обязательная выгрузка; эксперт сверяет файл с экраном.

**Контракт:** `ExportSearchRequest {context, search_id, format: XLSX|DOCX, filter: ResultFilter, sort: ResultSort}`
→ `ExportSearchResponse {content: bytes, filename: str, mime_type: str}`;
mime XLSX `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, DOCX
`application/vnd.openxmlformats-officedocument.wordprocessingml.document`. Строки берутся **тем же**
кодом, что `ListResults` (один query-хэндлер, без limit) — тогда файл гарантированно совпадает с экраном.
Размер: до ~2000 строк укладывается в лимит gRPC 4 МБ; больше — поднять `grpc.max_send_message_length`.

**Формат** (`openpyxl`), лист «Подборка»:
- Шапка: Запрос · Как понят запрос (summary) · Период (дд.мм.гггг — дд.мм.гггг, время Красноярска) ·
  Режим (по выбранным источникам / без ограничения списком) · Площадки · Сформировано · **Публикаций
  в подборке: N** (из них без даты: K; исключено вручную: M).
- Таблица: № · Площадка · Источник · Ссылка на источник · Заголовок / начало поста · Дата публикации
  («недоступна») · **Ссылка на публикацию** (кликабельная, `cell.hyperlink` + стиль Hyperlink) ·
  Выдержка · Связь с запросом (прямая/косвенная/спорная) · Почему · Регион · Тональность · Сюжет №.
- Закрепить шапку таблицы, автофильтр, ширины колонок, перенос текста.
- Лист «Охват»: каждая цель — площадка, источник, статус, получено, в подборке, ошибка.

Тот же фильтр и сортировка, что на экране (приходят в запросе); исключённые не попадают.
Имя файла ASCII: `podborka_2026-10-19_<id8>.xlsx`.

**DoD.** Тест: экспорт → прочитать openpyxl → число строк = `counts.total`, ссылки = `results[].url`
в том же порядке.

### [ ] B2-09 · P0 · к H+18 · исключение, повтор, отмена
**Контракт:**
```
SetExcludedRequest  { context, search_id, result_ids: str[], excluded: bool } -> { counts: SearchCounts }
                      # чужой/несуществующий result_id → RESULT_NOT_FOUND
RetrySearchRequest  { context, search_id, target_ids: str[] (пусто = все FAILED) } -> { search: Search }
CancelSearchRequest { context, search_id } -> { search: Search }
```
`SetExcluded` (пачкой) → пересчитанные `counts`. `RetrySearch`: только `FAILED` цели (или указанные),
`attempts += 1`, статус поиска обратно `RUNNING`, затем снова scoring/grouping по новым постам и
финальный статус; `SEARCH_NOT_FINISHED`, если поиск ещё идёт. `CancelSearch` — отменить задачу,
незавершённые цели → `SKIPPED`.

### [ ] B2-10 · P2 · к H+32 · импорт XLSX и DOCX
**Контракт:** `ImportSourcesRequest {context, xlsx: bytes}` → `ImportSourcesResponse {created: uint32,
duplicates: uint32, failed: [{row: uint32 (номер строки Excel, с 1), value: str, error: {code, message}}]}`.
`ImportSources`: строки → `CreateSource` по одной, отчёт created/duplicates/failed с номером строки.
`ExportSearch(format=DOCX)` (`python-docx`): шапка как в XLSX + список публикаций (заголовок-ссылка,
источник, дата, выдержка).

### [ ] B2-11 · P1 · к H+36 · метрики для презентации
В `Search` — время по стадиям (лог + `warnings` не трогаем; отдельное поле не нужно — достаточно
`started_at/finished_at` и лога с длительностями стадий). Дать TL цифры: среднее время поиска
на 30 источниках.
