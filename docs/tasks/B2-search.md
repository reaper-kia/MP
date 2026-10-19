# B2 — search_service (ядро: источники, поиски, подборка, экспорт)

Зона: `services/search_service/**`. Контракт: `contracts/search/v1/search_service.proto`.
Сервис создаёт TL (`make new-service name=search entity=Source`), дальше — твой. Стиль шаблона:
domain → applications (commands/queries/handlers/ports) → infra → transport.
Модель данных и пайплайн — [ARCHITECTURE.md §3–5](../ARCHITECTURE.md). Это **самый нагруженный
сервис по критериям**: достоверность и учёт (10), архитектура и модель данных (3), сценарии 3–5.

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

**DoD.** Миграция применяется на чистой БД; тесты на переходы статусов.

### [ ] B2-02 · P0 · к H+5 · источники
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

### [ ] B2-04 · P0 · к H+8 · пайплайн
**Цель.** Сердце продукта. Устойчиво, параллельно, с честными статусами.

**Сделать.**
1. `SearchRunner` (infra): реестр `asyncio.Task` по `search_id`, запуск/отмена; при старте сервиса
   все `RUNNING/QUEUED` → `FAILED` с warning «Поиск прерван перезапуском сервиса».
2. Стадии по ARCHITECTURE §3: analyzing_query → collecting → scoring → grouping → done; `stage`
   и прогресс пишутся в БД после каждой цели (фронт опрашивает).
3. Сбор: `asyncio.Semaphore(5)`, таймаут на цель (60 с), ошибка цели → `mark_failed(code, message)`
   с **русским** сообщением для пользователя («Одноклассники не ответили за 60 секунд»), поиск идёт дальше.
4. Каждая цель после сбора сразу сохраняет посты (B2-05) — частичный результат виден во время поиска
   и сохраняется при падении остальных.
5. Короткие транзакции: внешние вызовы (collector, ml) **вне** открытого UoW.

**DoD (тесты на фейках).** 3 цели, одна падает → `PARTIAL`, посты двух других сохранены;
все падают → `FAILED`; 0 постов везде → `COMPLETED`, `total=0`; отмена → `CANCELLED`.

### [ ] B2-05 · P0 · к H+10 · сохранение, дедуп, период, заголовок, выдержка
**Цель.** Критерий «Достоверность и учёт» (10 баллов) живёт здесь.

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
`AnalyzeQuery` → `query_type`, `query_analysis`, фразы для `SearchPlatform`; ML недоступен →
фразы = `[query]` и warning. `ScorePosts` батчами по 30, параллельно ≤ 3 батча; таймаут 60 с;
упал батч → эти посты `DISPUTED` с explanation «Не удалось проверить автоматически — проверьте вручную»
(не теряем, не выдумываем). `GroupPosts` — по прошедшим отбор; упал → без групп.
Регион в `global`: `irrelevant`, если нет ни `by_source`, ни `by_content` (объяснение — от нас).

### [ ] B2-07 · P0 · к H+10 · выдача
`ListResults`: фильтры `relevance` (по умолчанию direct+indirect+disputed), `platforms`, `target_ids`,
`date_status`, `include_excluded`; сортировки; `total`, `has_more`. `ListGroups`: группы с **полным**
списком размещений. Счётчики `SearchCounts` — одним SQL с `COUNT(*) FILTER (WHERE …)`.
`matched` у цели = сколько её постов в подборке.

### [ ] B2-08 · P0 · к H+12 · экспорт XLSX
**Цель.** Обязательная выгрузка; эксперт сверяет файл с экраном.

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
`SetExcluded` (пачкой) → пересчитанные `counts`. `RetrySearch`: только `FAILED` цели (или указанные),
`attempts += 1`, статус поиска обратно `RUNNING`, затем снова scoring/grouping по новым постам и
финальный статус; `SEARCH_NOT_FINISHED`, если поиск ещё идёт. `CancelSearch` — отменить задачу,
незавершённые цели → `SKIPPED`.

### [ ] B2-10 · P2 · к H+32 · импорт XLSX и DOCX
`ImportSources`: строки → `CreateSource` по одной, отчёт created/duplicates/failed с номером строки.
`ExportSearch(format=DOCX)` (`python-docx`): шапка как в XLSX + список публикаций (заголовок-ссылка,
источник, дата, выдержка).

### [ ] B2-11 · P1 · к H+36 · метрики для презентации
В `Search` — время по стадиям (лог + `warnings` не трогаем; отдельное поле не нужно — достаточно
`started_at/finished_at` и лога с длительностями стадий). Дать TL цифры: среднее время поиска
на 30 источниках.
