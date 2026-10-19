# TL — тимлид / DevOps / gateway

Зона: `contracts/**`, `services/gateway/**`, `compose.yaml`, `infra/**`, `.github/**`, `Makefile`,
`README.md`, `docs/**`. Твоя главная работа — **чтобы все остальные не ждали**: контракты, стабы,
интеграция, доступы, демо.

---

### [ ] TL-01 · P0 · к H+1 · каркас сервисов
**Цель.** Три новых сервиса существуют, поднимаются в compose и видны в `/health/ready`.

**Сделать.**
1. `make new-service name=search entity=Source port=50053 db_port=5435`
2. `make new-service name=collector port=50054`, `make new-service name=ml port=50055`; у обоих убрать БД:
   `migrations/`, `alembic.ini`, `infra/database`, `infra/repositories`, `infra/uow`, alembic из Dockerfile
   и из `make run` (в Makefile: запускать `alembic upgrade head`, только если есть `alembic.ini`).
3. Убрать `auth_client` из collector/ml (README §8, последний абзац).
4. `compose.yaml`: `search_service`+`search_db`, `collector_service`, `ml_service`; gateway —
   `SEARCH_GRPC_TARGET`, `COLLECTOR_GRPC_TARGET`, `ML_GRPC_TARGET`; search_service — адреса collector и ml.
   Профиль `llm-local` с контейнером `ollama` (для ML без ключей Яндекса).
5. CI matrix — три новых сервиса. `.env.example` — `SEARCH_DB_PASSWORD`, `VK_SERVICE_TOKEN`,
   `YC_FOLDER_ID`, `YC_API_KEY`, `YC_SEARCH_API_KEY`, `LLM_PROVIDER`, `COLLECTOR_FAKE`.
6. Удалить `example_service` (README §18) — **после** создания сервисов.
7. Запушить в main, написать в чат «каркас готов, тянем».

**DoD.** `make up` → все контейнеры healthy; `curl :8000/health/ready` показывает search/collector/ml;
`make check` зелёный.

### [ ] TL-02 · P0 · к H+2 · контракты v1 — заморозка
**Цель.** Все пишут код по одному контракту с первого часа.

**Сделать.**
1. 30 минут с командой пройти `contracts/http/openapi.yaml` (с FE), `search_service.proto` (с B2),
   `collector_service.proto` (с B1), `ml_service.proto` (с ML). Правки — сразу.
2. `make proto`, коммит сгенерированного кода. Перегенерировать справочники:
   `python3 scripts/gen_api_docs.py && python3 scripts/gen_grpc_docs.py` → `docs/API.md`, `docs/api-types.ts`,
   `docs/GRPC.md` (делать после **каждой** правки контракта; можно добавить в `make proto`).
3. Поднять у себя Prism (`npx @stoplight/prism-cli@5 mock contracts/http/openapi.yaml -p 4010`) — проверить,
   что FE реально может на нём работать.
4. Объявить «контракт v1 заморожен». Дальше правки только через тебя: правка → `make proto` → сообщение
   в чат, что изменилось.

**DoD.** Сгенерированный код в `packages/platform_contracts` свежий (CI проверяет); FE получил ответы от Prism.

### [ ] TL-03 · P0 · к H+6 · роутеры gateway
**Цель.** Каждая ручка из `openapi.yaml` существует и проксирует в search_service (а `/platforms` — в collector
через search или напрямую — реши; проще напрямую в collector, `/query/analyze` — напрямую в ml).

**Сделать.**
1. `grpc_clients.py`: `search`, `collector`, `ml`. Таймауты: по умолчанию 5 с; `ExportSearch` 60 с;
   `ResolveSource`/`CreateSource` 20 с; `AnalyzeQuery` 20 с.
2. Роутеры `routers/meta.py`, `sources.py`, `searches.py`, `results.py`; схемы pydantic в `schemas/`
   **один к одному с openapi.yaml** (имена полей, enum'ы, `null`).
3. Маппинг enum proto ⇄ HTTP в одном месте (`schemas/enums.py`), в т.ч. `RELEVANCE_IRRELEVANT` ⇄ `"rejected"`,
   `optional` поля proto → `null`.
4. Ручки анонимные (`AnonCtx`). CORS: `http://localhost:5173` + `chrome-extension://*` (для FE-10).
5. Экспорт: `StreamingResponse`/`Response` с `Content-Disposition: attachment; filename*=UTF-8''…`.
6. Импорт: `UploadFile` → `bytes` → `ImportSources`.
7. Ошибки новых кодов — в таблицу маппинга gateway (`RESOURCE_EXHAUSTED` → 429). Для
   `SEARCH_INVALID_PARAMS` сообщение вида `"period_from: …"` разложить в `details: [{field, message}]`.
8. Тесты gateway с подменёнными стабами (как в шаблоне) — хотя бы по одному на роутер.

**Контракт: HTTP → gRPC** (поля HTTP — [`docs/API.md`](../API.md), поля gRPC — [`docs/GRPC.md`](../GRPC.md)).

| HTTP (operationId) | gRPC | Маппинг, на что смотреть |
|---|---|---|
| `GET /platforms` (listPlatforms) | `collector.v1.CollectorService/GetPlatforms` | `PlatformInfo`: `code`←`platform`, `source_mode`←`source_mode_supported`, `global_mode`←`global_mode_supported`, `status`←`health`, `note` пусто → `null` |
| `POST /query/analyze` (analyzeQuery) | `ml.v1.MlService/AnalyzeQuery` | отдаём подмножество `QueryAnalysis`: `query_type, summary, search_queries, needs_clarification, clarification_hint` (пусто → `null`) |
| `GET /sources` (listSources) | `search.v1.SearchService/ListSources` | `platform[]`→`platforms`, `items`←`sources` |
| `POST /sources/resolve` | `SearchService/ResolveSource` | `SourcePreview` 1:1, `optional` → `null` |
| `POST /sources` (createSource) | `SearchService/CreateSource` | `is_regional` по умолчанию `true` (в proto bool, по умолчанию false — подставить в gateway!) |
| `PATCH /sources/{id}` | `SearchService/UpdateSource` | ставить в proto только присланные поля (`model_fields_set`) |
| `DELETE /sources/{id}` | `SearchService/DeleteSource` | 204 |
| `POST /sources/import` | `SearchService/ImportSources` | `UploadFile.read()` → `xlsx`; `failed[]`: `{row, value, code←error.code, message←error.message}` |
| `POST /searches` (startSearch) | `SearchService/StartSearch` | **202**; `mode`, `platforms` → enum |
| `GET /searches` (listSearches) | `SearchService/ListSearches` | `Search` → `SearchSummary` (`id, status, params, counts, created_at, finished_at`) |
| `GET /searches/{id}` | `SearchService/GetSearch` | `Search` целиком |
| `POST /searches/{id}/retry` | `SearchService/RetrySearch` | **202**; тело необязательно |
| `POST /searches/{id}/cancel` | `SearchService/CancelSearch` | |
| `GET /searches/{id}/results` | `SearchService/ListResults` | query → `ResultFilter{relevance, platforms, target_ids, date_status, include_excluded}` + `ResultSort`; `items`←`results` |
| `GET /searches/{id}/groups` | `SearchService/ListGroups` | `items`←`groups`, `ResultGroup.items`←`results` |
| `POST /searches/{id}/results/exclusion` | `SearchService/SetExcluded` | `{counts}` |
| `GET /searches/{id}/export` | `SearchService/ExportSearch` | `Response(content, media_type=mime_type, headers=Content-Disposition(filename))` |

**Enum'ы proto → HTTP** (один модуль `schemas/enums.py`): общее правило — убрать префикс и в нижний
регистр (`PLATFORM_VK`→`vk`, `SEARCH_STATUS_PARTIAL`→`partial`, `SEARCH_STAGE_ANALYZING_QUERY`→
`analyzing_query`, `TARGET_KIND_PLATFORM_SEARCH`→`platform_search`, `TITLE_SOURCE_POST_START`→
`post_start`, `DATE_STATUS_IN_PERIOD`→`in_period`, `RESULT_SORT_DATE_DESC`→`date_desc`). Исключения:
`RELEVANCE_IRRELEVANT` ⇄ `"rejected"`; `SENTIMENT_UNSPECIFIED` → `null`; `QUERY_TYPE_UNSPECIFIED` → `null`;
`PLATFORM_HEALTH_*` → `ok|degraded|unavailable`. `Timestamp` → ISO UTC (`ts()` из `schemas/common.py`);
`optional` без значения → `null`; `optional ErrorInfo error` без значения → `null`.

**DoD.** Swagger `/docs` совпадает с `openapi.yaml` (сверить глазами по списку путей и полям `Search`, `Result`);
FE переключает proxy с Prism на gateway и ничего не ломается.

### [ ] TL-04 · P0 · к H+4 · доступы
**Цель.** Ключи есть у тех, кому нужны, до того как они упрутся.

**Сделать.** VK ID приложение → сервисный ключ (B1). Yandex Cloud: каталог, сервисный аккаунт, API-ключ,
роли `ai.languageModels.user` и для Search API (ML, B1) — проверь грант/бюджет. Сервер для демо.
Стартовые материалы кейса (список источников, сайтов, «согласованные доступы») — как придут, в
`docs/ARCHITECTURE.md §7` и в `.env` на сервере.

**DoD.** Таблица §7 в ARCHITECTURE заполнена, у каждого рабочий ключ в локальном `.env`.

### [ ] TL-05 · P0 · к H+12 и H+24 · интеграционный прогон
**Цель.** Ловить несостыковки на вехах, а не на демо.

**Сделать.** На H+6, H+12, H+24, H+34 пройти 5 сценариев ТЗ руками по чек-листу `docs/demo/checklist.md`
(создай его: сценарий → действия → ожидаемое). Баги — в чат с ID задачи владельца.
Обновить `scripts/smoke.py`: создать источник → поиск → дождаться финального статуса → results → export
(проверить, что XLSX открывается openpyxl и число строк = `counts.total`).

**DoD.** `make smoke` проходит на стенде; чек-лист с отметками по каждой вехе.

### [ ] TL-06 · P0 · к H+14 · каталог источников (seed)
**Цель.** Режим «везде» и демо работают на реальных региональных источниках.

**Сделать.** Из стартовых материалов (или вручную, если их нет — 30–50 источников: крупные СМИ края,
правительство, ГИБДД/МЧС края, мэрии крупных городов в VK, OK, MAX) → `seed/sources.xlsx`
(A — ссылка, B — название, C — региональный). Загрузка через `POST /sources/import` (B2-10) или скриптом
`scripts/seed_sources.py`, который дёргает `POST /sources` по строкам (это P0-путь, импорт — P2).

**DoD.** После `make reset && make up && make seed` в каталоге ≥ 30 источников, у всех `name` с площадки.

### [ ] TL-07 · P0 · к H+30 · деплой
**Сделать.** `make deploy HOST=…`; `.env` на сервере с ключами; `COLLECTOR_FAKE=false`, проверка в
`/health/ready`; фронт и расширение смотрят на адрес сервера. Ежедневный (ежечасный перед демо)
`make smoke URL=…`.

**DoD.** Эксперт открывает `http://<ip>` и проходит сценарий 1 без нас.

### [ ] TL-08 · P0 · к H+38 · README по требованиям ТЗ
**Цель.** Критерий «Документация» (2) + условия сдачи. Эксперт по README запускает и проверяет.

**Сделать.** Разделы (каждый — коротко, по делу):
1. Что это и для кого; 5 шагов пользователя со скриншотами.
2. Как запустить: веб (адрес стенда), локально (`make install && make up && make seed`), расширение
   (chrome://extensions → «Загрузить распакованное», без прав администратора).
3. Поддерживаемые площадки: как получаем данные с каждой (из B1-10), ограничения.
4. Как отбираем по смыслу, как учитываем регион, как исключаем повторный учёт поста (из ARCHITECTURE §5).
5. Модели и внешние сервисы: какие, настройки, **какие данные передаются**, стоимость (из ML-09).
6. Доступы для экспертов: всё уже настроено на стенде, подписки покупать не нужно.
7. Демо-запросы и примеры выгрузок: `docs/demo/` (XLSX-файлы реальных прогонов).
8. **Работает / имитация / план** — таблица `docs/STATUS.md`.
9. Известные ограничения.

**DoD.** Человек не из команды по README поднимает локально и проходит сценарий 1.

### [ ] TL-09 · P0 · к H+44 · демо и презентация
**Сделать.** Сценарий показа на одном сквозном примере (критерий «Демонстрация» 5 баллов): запрос →
период → источники → поиск (видно прогресс и охват) → спорные → открыть 2–3 ссылки → исключить →
XLSX → открыть файл. Отдельно: сценарий 2 (текст новости), сценарий 5 (отключённый источник).
Слайд «Качество» — таблица precision/recall/время из ML-09. Два прогона на сервере; видео-страховка.
Разделить вопросы: кто отвечает про сбор (B1), отбор (ML), архитектуру (TL), UX (FE).

**DoD.** Прогон укладывается в регламент, каждый знает свою часть.

### [ ] TL-10 · P1 · по ходу · ревью и «проверенное vs предположения»
Ревьюить PR в `main` (приоритет: контрактные и B2). Вести `docs/STATUS.md` — что реально проверено,
что предположение (критерий «Выступление и ответы»).
