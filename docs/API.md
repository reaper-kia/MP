# HTTP API — справочник (сгенерирован из `contracts/http/openapi.yaml`)

> Не править руками. Источник правды — `openapi.yaml`; после его изменения: `make docs` (или `make proto`).

Версия контракта: **1.0.0**. Базовый URL: gateway `http://localhost:8000`, мок Prism `http://localhost:4010`.

Общие правила:

- Авторизации нет (по ТЗ регистрация не нужна). Все ручки анонимные.
- Даты периода — `YYYY-MM-DD` в часовом поясе Asia/Krasnoyarsk, обе границы включительно.
- Время (`*_at`) — ISO 8601 в UTC; показывать в Asia/Krasnoyarsk.
- Поле `null` = «недоступно». Фронт показывает «нет данных», а не пустоту и не 0.
- Ошибка всегда `{"error": {"code", "message", "request_id", "details"}}`; фронт решает по `code`.
- Пагинация: `limit` + `offset` → `{items, total, has_more}`. Исключение — история поисков
  `GET /searches`: `{items, has_more}` без `total`.
- Любая ручка может ответить `429 RATE_LIMITED` (площадка ограничила частоту запросов — повторить позже)
  и `501 NOT_IMPLEMENTED` (возможность ещё не включена, например DOCX). Показывать `message` как есть.

TypeScript-типы всех схем — [`api-types.ts`](api-types.ts) (для фронта предпочтительно генерировать `openapi-typescript`, этот файл — для чтения).

## Содержание

| Метод | Путь | operationId | Что делает |
|---|---|---|---|
| GET | `/api/v1/platforms` | [listPlatforms](#listplatforms) | Площадки и их доступность |
| POST | `/api/v1/query/analyze` | [analyzeQuery](#analyzequery) | Как система поняла запрос (подсказка до запуска) |
| GET | `/api/v1/sources` | [listSources](#listsources) | Каталог источников |
| POST | `/api/v1/sources` | [createSource](#createsource) | Добавить источник по ссылке |
| POST | `/api/v1/sources/resolve` | [resolveSource](#resolvesource) | Предпросмотр источника по ссылке (до сохранения) |
| POST | `/api/v1/sources/import` | [importSources](#importsources) | [необязательно] Импорт списка из Excel |
| PATCH | `/api/v1/sources/{source_id}` | [updateSource](#updatesource) | Изменить источник (название, флаги, заметка) |
| DELETE | `/api/v1/sources/{source_id}` | [deleteSource](#deletesource) | Удалить источник (мягко — история поисков сохраняет снимок) |
| GET | `/api/v1/searches` | [listSearches](#listsearches) | История поисков |
| POST | `/api/v1/searches` | [startSearch](#startsearch) | Запустить поиск |
| GET | `/api/v1/searches/{search_id}` | [getSearch](#getsearch) | Статус, охват и счётчики поиска |
| POST | `/api/v1/searches/{search_id}/retry` | [retrySearch](#retrysearch) | Повторить упавшие источники |
| POST | `/api/v1/searches/{search_id}/cancel` | [cancelSearch](#cancelsearch) | Остановить поиск (незавершённые источники → skipped) |
| GET | `/api/v1/searches/{search_id}/results` | [listResults](#listresults) | Подборка (плоский список) |
| GET | `/api/v1/searches/{search_id}/groups` | [listGroups](#listgroups) | Подборка, сгруппированная по сюжетам |
| POST | `/api/v1/searches/{search_id}/results/exclusion` | [setExcluded](#setexcluded) | Исключить / вернуть публикации (одну, несколько или всю группу) |
| GET | `/api/v1/searches/{search_id}/export` | [exportSearch](#exportsearch) | Выгрузка XLSX (обязательно) / DOCX (по желанию) |

## listPlatforms

**`GET /api/v1/platforms`** — Площадки и их доступность

Показывать в форме поиска (чекбоксы площадок) и в блоке «Охват». Если `status=unavailable` — чекбокс выключен с подсказкой `note`.

Ответы:

| Код | Тело |
|---|---|
| 200 | [`PlatformInfo`](#platforminfo)[] |

## analyzeQuery

**`POST /api/v1/query/analyze`** — Как система поняла запрос (подсказка до запуска)

Вызывать с debounce ~800 мс после ввода. Показывать `summary` и тип запроса; если `needs_clarification` — мягкую подсказку `clarification_hint`. Не блокирует кнопку «Найти».

Тело (`application/json`): [`QueryAnalyzeIn`](#queryanalyzein)

```json
{
  "query": "Безопасность дорожного движения в Красноярском крае"
}
```

Ответы:

| Код | Тело |
|---|---|
| 200 | [`QueryAnalysis`](#queryanalysis) |
| 422 | [`ErrorResponse`](#errorresponse) (Неверные данные (SEARCH_INVALID_PARAMS, UNSUPPORTED_URL, VALIDATION_ERROR)) |

## listSources

**`GET /api/v1/sources`** — Каталог источников

Параметры:

| Имя | Где | Тип | Обяз. | Описание |
|---|---|---|---|---|
| `platform` | query | [`Platform`](#platform)[] | нет | повторять: `?platform=a&platform=b` |
| `q` | query | string | нет | Поиск по названию/ссылке |
| `is_active` | query | boolean | нет |  |
| `limit` | query | integer | нет | по умолчанию `50`; мин. 1; макс. 200 |
| `offset` | query | integer | нет | по умолчанию `0`; мин. 0 |

Ответы:

| Код | Тело |
|---|---|
| 200 | [`SourcePage`](#sourcepage) |

## createSource

**`POST /api/v1/sources`** — Добавить источник по ссылке

Тело (`application/json`): [`SourceCreateIn`](#sourcecreatein)

```json
{
  "url": "https://vk.com/krsk_news",
  "is_regional": true
}
```

Ответы:

| Код | Тело |
|---|---|
| 201 | [`Source`](#source) |
| 409 | [`ErrorResponse`](#errorresponse) (Конфликт (SOURCE_ALREADY_EXISTS, SEARCH_NOT_FINISHED)) |
| 422 | [`ErrorResponse`](#errorresponse) (Неверные данные (SEARCH_INVALID_PARAMS, UNSUPPORTED_URL, VALIDATION_ERROR)) |
| 429 | [`ErrorResponse`](#errorresponse) (Площадка ограничила частоту запросов (RATE_LIMITED) — повторить позже) |
| 503 | [`ErrorResponse`](#errorresponse) (Площадка или сервис недоступны (PLATFORM_UNAVAILABLE, SERVICE_UNAVAILABLE)) |

## resolveSource

**`POST /api/v1/sources/resolve`** — Предпросмотр источника по ссылке (до сохранения)

Пользователь вставил ссылку → показываем название, площадку, город, и если уже есть в каталоге — «Уже в списке».

Тело (`application/json`): [`SourceResolveIn`](#sourceresolvein)

```json
{
  "url": "vk.com/krsk_news"
}
```

Ответы:

| Код | Тело |
|---|---|
| 200 | [`SourcePreview`](#sourcepreview) |
| 404 | [`ErrorResponse`](#errorresponse) (Не найдено (SEARCH_NOT_FOUND, SOURCE_NOT_FOUND, RESULT_NOT_FOUND)) |
| 422 | [`ErrorResponse`](#errorresponse) (Неверные данные (SEARCH_INVALID_PARAMS, UNSUPPORTED_URL, VALIDATION_ERROR)) |
| 429 | [`ErrorResponse`](#errorresponse) (Площадка ограничила частоту запросов (RATE_LIMITED) — повторить позже) |
| 503 | [`ErrorResponse`](#errorresponse) (Площадка или сервис недоступны (PLATFORM_UNAVAILABLE, SERVICE_UNAVAILABLE)) |

## importSources

**`POST /api/v1/sources/import`** — [необязательно] Импорт списка из Excel

Тело (`multipart/form-data`): 

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `file` | string (binary) | да | .xlsx: A — ссылка, B — название, C — региональный (да/нет) |

Ответы:

| Код | Тело |
|---|---|
| 200 | [`SourceImportReport`](#sourceimportreport) |
| 422 | [`ErrorResponse`](#errorresponse) (Неверные данные (SEARCH_INVALID_PARAMS, UNSUPPORTED_URL, VALIDATION_ERROR)) |

## updateSource

**`PATCH /api/v1/sources/{source_id}`** — Изменить источник (название, флаги, заметка)

Параметры:

| Имя | Где | Тип | Обяз. | Описание |
|---|---|---|---|---|
| `source_id` | path | string (uuid) | да |  |

Тело (`application/json`): [`SourceUpdateIn`](#sourceupdatein)

```json
{
  "is_active": false
}
```

Ответы:

| Код | Тело |
|---|---|
| 200 | [`Source`](#source) |
| 404 | [`ErrorResponse`](#errorresponse) (Не найдено (SEARCH_NOT_FOUND, SOURCE_NOT_FOUND, RESULT_NOT_FOUND)) |

## deleteSource

**`DELETE /api/v1/sources/{source_id}`** — Удалить источник (мягко — история поисков сохраняет снимок)

Параметры:

| Имя | Где | Тип | Обяз. | Описание |
|---|---|---|---|---|
| `source_id` | path | string (uuid) | да |  |

Ответы:

| Код | Тело |
|---|---|
| 204 | Удалён |
| 404 | [`ErrorResponse`](#errorresponse) (Не найдено (SEARCH_NOT_FOUND, SOURCE_NOT_FOUND, RESULT_NOT_FOUND)) |

## listSearches

**`GET /api/v1/searches`** — История поисков

Параметры:

| Имя | Где | Тип | Обяз. | Описание |
|---|---|---|---|---|
| `limit` | query | integer | нет | по умолчанию `50`; мин. 1; макс. 200 |
| `offset` | query | integer | нет | по умолчанию `0`; мин. 0 |

Ответы:

| Код | Тело |
|---|---|
| 200 | [`SearchSummaryPage`](#searchsummarypage) |

## startSearch

**`POST /api/v1/searches`** — Запустить поиск

Возвращает задачу сразу (`status=queued`). Дальше фронт опрашивает `GET /searches/{id}`
каждые 1.5 с, пока `status` не станет одним из `completed | partial | failed | cancelled`.
id текущего поиска держать в URL (`/search/<id>`) — так подборка всегда привязана к своим параметрам.

`mode=selected`: ищем только по `source_ids`, площадки берутся из самих источников, а `platforms`
игнорируется (передавайте площадки этих источников). `mode=global`: `source_ids` пустой, ищем по
всей площадке из `platforms` и по активным источникам каталога.

Кэш (B2-20): такой же поиск (тот же запрос без учёта регистра и лишних пробелов, период, режим,
площадки / источники) уже завершился за последние 30 минут → в ответе сразу копия готовой
подборки: новый `id`, финальный `status`, `cache.from_search_id` и `cache.created_at` (когда
собрана). Показать плашку «Подборка из кэша · собрана N мин назад · Обновить»; «Обновить»
и «Повторить» шлют `fresh=true` — настоящий поиск мимо кэша.

Тело (`application/json`): [`SearchCreateIn`](#searchcreatein)

```json
{
  "query": "Безопасность дорожного движения в Красноярском крае",
  "period_from": "2026-10-01",
  "period_to": "2026-10-19",
  "mode": "selected",
  "platforms": [
    "vk",
    "ok",
    "max"
  ],
  "source_ids": [
    "5b0e2f6e-1c1a-4c47-9a39-6a1b2f0b0a01",
    "5b0e2f6e-1c1a-4c47-9a39-6a1b2f0b0a02"
  ]
}
```

Ответы:

| Код | Тело |
|---|---|
| 202 | [`Search`](#search) |
| 422 | [`ErrorResponse`](#errorresponse) (Неверные данные (SEARCH_INVALID_PARAMS, UNSUPPORTED_URL, VALIDATION_ERROR)) |

## getSearch

**`GET /api/v1/searches/{search_id}`** — Статус, охват и счётчики поиска

Параметры:

| Имя | Где | Тип | Обяз. | Описание |
|---|---|---|---|---|
| `search_id` | path | string (uuid) | да |  |

Ответы:

| Код | Тело |
|---|---|
| 200 | [`Search`](#search) |
| 404 | [`ErrorResponse`](#errorresponse) (Не найдено (SEARCH_NOT_FOUND, SOURCE_NOT_FOUND, RESULT_NOT_FOUND)) |

## retrySearch

**`POST /api/v1/searches/{search_id}/retry`** — Повторить упавшие источники

Найденное раньше сохраняется. Кнопка «Повторить» у каждой упавшей цели и общая «Повторить все неудачные».

Параметры:

| Имя | Где | Тип | Обяз. | Описание |
|---|---|---|---|---|
| `search_id` | path | string (uuid) | да |  |

Тело (`application/json`): 

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `target_ids` | string[] | нет | Пусто — все failed |

Ответы:

| Код | Тело |
|---|---|
| 202 | [`Search`](#search) |
| 404 | [`ErrorResponse`](#errorresponse) (Не найдено (SEARCH_NOT_FOUND, SOURCE_NOT_FOUND, RESULT_NOT_FOUND)) |
| 409 | [`ErrorResponse`](#errorresponse) (Конфликт (SOURCE_ALREADY_EXISTS, SEARCH_NOT_FINISHED)) |

## cancelSearch

**`POST /api/v1/searches/{search_id}/cancel`** — Остановить поиск (незавершённые источники → skipped)

Если поиск уже завершён (`completed | partial | failed | cancelled`) — ничего не меняет, отвечает 200 с текущим состоянием, не ошибкой.

Параметры:

| Имя | Где | Тип | Обяз. | Описание |
|---|---|---|---|---|
| `search_id` | path | string (uuid) | да |  |

Ответы:

| Код | Тело |
|---|---|
| 200 | [`Search`](#search) |
| 404 | [`ErrorResponse`](#errorresponse) (Не найдено (SEARCH_NOT_FOUND, SOURCE_NOT_FOUND, RESULT_NOT_FOUND)) |

## listResults

**`GET /api/v1/searches/{search_id}/results`** — Подборка (плоский список)

Можно запрашивать во время `running` — результаты появляются по мере обработки.

Параметры:

| Имя | Где | Тип | Обяз. | Описание |
|---|---|---|---|---|
| `search_id` | path | string (uuid) | да |  |
| `relevance` | query | [`Relevance`](#relevance)[] | нет | По умолчанию direct+indirect+disputed. `rejected` — вкладка «Отсеяно системой».; повторять: `?relevance=a&relevance=b` |
| `platform` | query | [`Platform`](#platform)[] | нет | повторять: `?platform=a&platform=b` |
| `target_id` | query | string[] | нет | Показать найденное в конкретном источнике (клик по строке в «Охвате»); повторять: `?target_id=a&target_id=b` |
| `date_status` | query | [`DateStatus`](#datestatus)[] | нет | повторять: `?date_status=a&date_status=b` |
| `include_excluded` | query | boolean | нет | по умолчанию `false` |
| `sort` | query | `relevance` \| `date_desc` \| `date_asc` | нет | по умолчанию `"relevance"` |
| `limit` | query | integer | нет | по умолчанию `50`; мин. 1; макс. 200 |
| `offset` | query | integer | нет | по умолчанию `0`; мин. 0 |

Ответы:

| Код | Тело |
|---|---|
| 200 | [`ResultPage`](#resultpage) |
| 404 | [`ErrorResponse`](#errorresponse) (Не найдено (SEARCH_NOT_FOUND, SOURCE_NOT_FOUND, RESULT_NOT_FOUND)) |

## listGroups

**`GET /api/v1/searches/{search_id}/groups`** — Подборка, сгруппированная по сюжетам

Одна новость в трёх группах = 1 сюжет из 3 размещений; в счётчике это 3 публикации. Все ссылки доступны внутри группы.

Параметры:

| Имя | Где | Тип | Обяз. | Описание |
|---|---|---|---|---|
| `search_id` | path | string (uuid) | да |  |
| `relevance` | query | [`Relevance`](#relevance)[] | нет | По умолчанию direct+indirect+disputed. `rejected` — вкладка «Отсеяно системой».; повторять: `?relevance=a&relevance=b` |
| `platform` | query | [`Platform`](#platform)[] | нет | повторять: `?platform=a&platform=b` |
| `target_id` | query | string[] | нет | Показать найденное в конкретном источнике (клик по строке в «Охвате»); повторять: `?target_id=a&target_id=b` |
| `date_status` | query | [`DateStatus`](#datestatus)[] | нет | повторять: `?date_status=a&date_status=b` |
| `include_excluded` | query | boolean | нет | по умолчанию `false` |
| `limit` | query | integer | нет | по умолчанию `50`; мин. 1; макс. 200 |
| `offset` | query | integer | нет | по умолчанию `0`; мин. 0 |

Ответы:

| Код | Тело |
|---|---|
| 200 | [`GroupPage`](#grouppage) |
| 404 | [`ErrorResponse`](#errorresponse) (Не найдено (SEARCH_NOT_FOUND, SOURCE_NOT_FOUND, RESULT_NOT_FOUND)) |

## setExcluded

**`POST /api/v1/searches/{search_id}/results/exclusion`** — Исключить / вернуть публикации (одну, несколько или всю группу)

Параметры:

| Имя | Где | Тип | Обяз. | Описание |
|---|---|---|---|---|
| `search_id` | path | string (uuid) | да |  |

Тело (`application/json`): [`ExclusionIn`](#exclusionin)

```json
{
  "result_ids": [
    "r-3"
  ],
  "excluded": true
}
```

Ответы:

| Код | Тело |
|---|---|
| 200 | `{ counts: SearchCounts }` |
| 404 | [`ErrorResponse`](#errorresponse) (Не найдено (SEARCH_NOT_FOUND, SOURCE_NOT_FOUND, RESULT_NOT_FOUND)) |

## exportSearch

**`GET /api/v1/searches/{search_id}/export`** — Выгрузка XLSX (обязательно) / DOCX (по желанию)

Передавать те же фильтры и сортировку, что на экране — файл должен совпадать с показанной подборкой. Исключённые не выгружаются. Скачивать через `<a href download>`.

Параметры:

| Имя | Где | Тип | Обяз. | Описание |
|---|---|---|---|---|
| `search_id` | path | string (uuid) | да |  |
| `format` | query | `xlsx` \| `docx` | да |  |
| `relevance` | query | [`Relevance`](#relevance)[] | нет | По умолчанию direct+indirect+disputed. `rejected` — вкладка «Отсеяно системой».; повторять: `?relevance=a&relevance=b` |
| `platform` | query | [`Platform`](#platform)[] | нет | повторять: `?platform=a&platform=b` |
| `target_id` | query | string[] | нет | Показать найденное в конкретном источнике (клик по строке в «Охвате»); повторять: `?target_id=a&target_id=b` |
| `date_status` | query | [`DateStatus`](#datestatus)[] | нет | повторять: `?date_status=a&date_status=b` |
| `sort` | query | `relevance` \| `date_desc` \| `date_asc` | нет | по умолчанию `"relevance"` |

Ответы:

| Код | Тело |
|---|---|
| 200 | файл: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| 404 | [`ErrorResponse`](#errorresponse) (Не найдено (SEARCH_NOT_FOUND, SOURCE_NOT_FOUND, RESULT_NOT_FOUND)) |
| 501 | [`ErrorResponse`](#errorresponse) (Возможность ещё не включена (NOT_IMPLEMENTED), например выгрузка в DOCX) |

# Схемы

## Platform

Значения: `vk`, `ok`, `max`, `news`

## Relevance

direct — прямо по запросу; indirect — косвенно; disputed — спорно, проверить; rejected — отсеяно системой (не в подборке)

Значения: `direct`, `indirect`, `disputed`, `rejected`

## DateStatus

Значения: `in_period`, `unknown`

## QueryType

Значения: `topic`, `event`, `person`, `news_text`

## ErrorResponse

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `error` | object (см. ниже) | да |  |

`error`:

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `code` | string | да |  |
| `message` | string | да |  |
| `request_id` | string | да |  |
| `details` | object[] | да |  |

## PlatformInfo

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `code` | [`Platform`](#platform) | да |  |
| `title` | string | да |  |
| `source_mode` | boolean | да | Поддерживает поиск по выбранным источникам |
| `global_mode` | boolean | да | Поддерживает поиск по всей площадке |
| `status` | `ok` \| `degraded` \| `unavailable` | да |  |
| `note` | string \| null | да |  |

## QueryAnalyzeIn

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `query` | string | да | мин. длина 3; макс. длина 20000 |

## QueryAnalysis

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `query_type` | [`QueryType`](#querytype) \| null | да | null — тип не определён (ML в упрощённом режиме): показать «тип запроса не определён» |
| `summary` | string | да |  |
| `search_queries` | string[] | да |  |
| `needs_clarification` | boolean | да |  |
| `clarification_hint` | string \| null | да |  |

<details><summary>Пример</summary>

```json
{
  "query_type": "topic",
  "summary": "Тема: безопасность дорожного движения (ДТП, ГИБДД, пешеходы) в Красноярском крае",
  "search_queries": [
    "безопасность дорожного движения",
    "ДТП Красноярск",
    "ГИБДД рейд",
    "пешеходный переход"
  ],
  "needs_clarification": false,
  "clarification_hint": null
}
```
</details>

## Source

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `id` | string (uuid) | да |  |
| `platform` | [`Platform`](#platform) | да |  |
| `external_id` | string | да |  |
| `url` | string (uri) | да |  |
| `name` | string | да |  |
| `city` | string \| null | да |  |
| `is_regional` | boolean | да | Относится к Красноярскому краю |
| `is_active` | boolean | да | Участвует в поиске «везде» и выбран по умолчанию |
| `notes` | string | да |  |
| `created_at` | string (date-time) | да |  |
| `updated_at` | string (date-time) | да |  |

<details><summary>Пример</summary>

```json
{
  "id": "5b0e2f6e-1c1a-4c47-9a39-6a1b2f0b0a01",
  "platform": "vk",
  "external_id": "-12345678",
  "url": "https://vk.com/krsk_news",
  "name": "Новости Красноярска",
  "city": "Красноярск",
  "is_regional": true,
  "is_active": true,
  "notes": "",
  "created_at": "2026-10-19T04:00:00Z",
  "updated_at": "2026-10-19T04:00:00Z"
}
```
</details>

## SourcePage

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `items` | [`Source`](#source)[] | да |  |
| `total` | integer | да |  |
| `has_more` | boolean | да |  |

## SourceCreateIn

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `url` | string | да | мин. длина 3 |
| `name` | string \| null | нет | Пусто — взять с площадки |
| `is_regional` | boolean | нет | по умолчанию `true` |
| `notes` | string | нет | по умолчанию `""` |

## SourceUpdateIn

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `name` | string | нет |  |
| `is_regional` | boolean | нет |  |
| `is_active` | boolean | нет |  |
| `notes` | string | нет |  |

## SourceResolveIn

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `url` | string | да | мин. длина 3 |

## SourcePreview

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `platform` | [`Platform`](#platform) | да |  |
| `external_id` | string | да |  |
| `url` | string | да |  |
| `name` | string | да |  |
| `city` | string \| null | да |  |
| `members_count` | integer \| null | да |  |
| `existing_source_id` | string \| null | да | Не null — уже в каталоге |

<details><summary>Пример</summary>

```json
{
  "platform": "vk",
  "external_id": "-12345678",
  "url": "https://vk.com/krsk_news",
  "name": "Новости Красноярска",
  "city": "Красноярск",
  "members_count": 184000,
  "existing_source_id": null
}
```
</details>

## SourceImportReport

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `created` | integer | да |  |
| `duplicates` | integer | да |  |
| `failed` | object (см. ниже)[] | да |  |

## SearchCreateIn

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `query` | string | да | Тема, событие, человек или текст новости — одно поле; мин. длина 3; макс. длина 20000 |
| `period_from` | string (date) | да |  |
| `period_to` | string (date) | да |  |
| `mode` | `selected` \| `global` | да |  |
| `platforms` | [`Platform`](#platform)[] | да | мин. элементов 1 |
| `source_ids` | string (uuid)[] | да | Обязательно непустой при mode=selected |
| `fresh` | boolean | нет | По умолчанию false. true — не брать готовую подборку из кэша, искать заново («Обновить») |

## SearchCache

Подборка взята из кэша — копия недавнего такого же поиска (B2-20)

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `from_search_id` | string (uuid) | да | Исходный поиск, с которого снята копия |
| `created_at` | string (date-time) | да | Когда исходный поиск завершился («собрана N мин назад») |

## SearchParams

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `query` | string | да |  |
| `query_type` | [`QueryType`](#querytype) \| null | да |  |
| `period_from` | string (date) | да |  |
| `period_to` | string (date) | да |  |
| `mode` | `selected` \| `global` | да |  |
| `platforms` | [`Platform`](#platform)[] | да |  |
| `source_ids` | string[] | да |  |

## SearchStatus

completed + counts.total=0 → «Подходящие публикации не найдены» (показать, где искали).
partial → подборка + баннер «Не удалось обработать N источников» + «Повторить».
failed → ошибка + «Повторить».

Значения: `queued`, `running`, `completed`, `partial`, `failed`, `cancelled`

## SearchStage

Подписи: Разбираем запрос… / Собираем публикации… / Проверяем связь с запросом… / Группируем…

Значения: `queued`, `analyzing_query`, `collecting`, `scoring`, `grouping`, `done`

## TargetStatus

done — найдены посты; empty — источник обработан, постов за период нет; failed — не удалось получить

Значения: `pending`, `running`, `done`, `empty`, `failed`, `skipped`

## ErrorInfo

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `code` | string | да | PLATFORM_UNAVAILABLE \| SOURCE_NOT_FOUND \| SOURCE_PRIVATE \| RATE_LIMITED \| TIMEOUT \| PARSE_ERROR \| AUTH_REQUIRED |
| `message` | string | да |  |

## SearchTarget

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `id` | string | да |  |
| `kind` | `source` \| `platform_search` | да |  |
| `platform` | [`Platform`](#platform) | да |  |
| `source_id` | string \| null | да |  |
| `name` | string | да | Снимок названия на момент поиска |
| `url` | string \| null | да |  |
| `status` | [`TargetStatus`](#targetstatus) | да |  |
| `fetched` | integer | да | Получено постов за период |
| `matched` | integer | да | Из них в подборке |
| `error` | [`ErrorInfo`](#errorinfo) \| null | да |  |
| `attempts` | integer | да |  |
| `finished_at` | string (date-time) \| null | да |  |

## SearchCounts

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `total` | integer | да | В подборке = direct+indirect+disputed минус исключённые. Каждое размещение считается отдельно. |
| `direct` | integer | да |  |
| `indirect` | integer | да |  |
| `disputed` | integer | да |  |
| `rejected` | integer | да | Отсеяно системой |
| `excluded` | integer | да | Исключено пользователем |
| `unknown_date` | integer | да | Из total — без даты публикации |
| `groups` | integer | да | Сюжетов среди total |

## Search

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `id` | string (uuid) | да |  |
| `status` | [`SearchStatus`](#searchstatus) | да |  |
| `stage` | [`SearchStage`](#searchstage) | да |  |
| `progress` | object (см. ниже) | да |  |
| `params` | [`SearchParams`](#searchparams) | да |  |
| `query_analysis` | [`QueryAnalysis`](#queryanalysis) \| null | да |  |
| `targets` | [`SearchTarget`](#searchtarget)[] | да |  |
| `counts` | [`SearchCounts`](#searchcounts) | да |  |
| `warnings` | string[] | да |  |
| `created_at` | string (date-time) | да |  |
| `started_at` | string (date-time) \| null | да |  |
| `finished_at` | string (date-time) \| null | да |  |
| `cache` | [`SearchCache`](#searchcache) \| null | да | Не null — подборка из кэша |

`progress`:

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `targets_total` | integer | да |  |
| `targets_finished` | integer | да |  |
| `percent` | integer | да | мин. 0; макс. 100 |

## SearchSummary

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `id` | string (uuid) | да |  |
| `status` | [`SearchStatus`](#searchstatus) | да |  |
| `params` | [`SearchParams`](#searchparams) | да |  |
| `counts` | [`SearchCounts`](#searchcounts) | да |  |
| `created_at` | string (date-time) | да |  |
| `finished_at` | string (date-time) \| null | да |  |

## SearchSummaryPage

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `items` | [`SearchSummary`](#searchsummary)[] | да |  |
| `has_more` | boolean | да |  |

## ExcerptPart

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `text` | string | да |  |
| `highlight` | boolean | да |  |

## Result

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `id` | string | да |  |
| `publication_id` | string | да |  |
| `platform` | [`Platform`](#platform) | да |  |
| `source` | object (см. ниже) | да |  |
| `url` | string | да | Прямая ссылка на пост |
| `title` | string | да |  |
| `title_source` | `title` \| `post_start` | да | post_start — заголовка нет, показано начало поста (пометить) |
| `excerpt` | string | да | Дословный фрагмент исходного текста |
| `excerpt_parts` | [`ExcerptPart`](#excerptpart)[] | да |  |
| `published_at` | string (date-time) \| null | да | null → «Дата недоступна» |
| `date_status` | [`DateStatus`](#datestatus) | да |  |
| `relevance` | [`Relevance`](#relevance) | да |  |
| `score` | number | да | мин. 0; макс. 1 |
| `explanation` | string | да | Почему система так решила |
| `region` | object (см. ниже) | да |  |
| `sentiment` | `positive` \| `neutral` \| `negative` \| null | да |  |
| `group_id` | string \| null | да |  |
| `group_size` | integer | да | Сколько размещений в сюжете (1 — одиночка) |
| `metrics` | object (см. ниже) | да |  |
| `excluded` | boolean | да |  |
| `found_by_target_id` | string | да |  |

`source`:

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `id` | string \| null | да | null — источник найден глобальным поиском и не в каталоге (можно предложить «Добавить в список») |
| `name` | string | да |  |
| `url` | string | да |  |
| `is_regional` | boolean | да |  |

`region`:

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `by_source` | boolean | да |  |
| `by_content` | boolean | да |  |
| `evidence` | string \| null | да | «Упоминается Ачинск» |

`metrics`:

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `views` | integer \| null | да |  |
| `likes` | integer \| null | да |  |
| `reposts` | integer \| null | да |  |
| `comments` | integer \| null | да |  |

<details><summary>Пример</summary>

```json
{
  "id": "r-1",
  "publication_id": "0c7d2c5e-3f1a-4b9e-8d6c-1a2b3c4d5e6f",
  "platform": "vk",
  "source": {
    "id": "5b0e2f6e-1c1a-4c47-9a39-6a1b2f0b0a01",
    "name": "Новости Красноярска",
    "url": "https://vk.com/krsk_news",
    "is_regional": true
  },
  "url": "https://vk.com/wall-12345678_98765",
  "title": "В Ачинске прошёл рейд «Пешеход»",
  "title_source": "post_start",
  "excerpt": "Сотрудники Госавтоинспекции проверили соблюдение правил на пешеходных переходах у школ…",
  "excerpt_parts": [
    {
      "text": "Сотрудники ",
      "highlight": false
    },
    {
      "text": "Госавтоинспекции",
      "highlight": true
    },
    {
      "text": " проверили соблюдение правил на ",
      "highlight": false
    },
    {
      "text": "пешеходных переходах",
      "highlight": true
    },
    {
      "text": " у школ…",
      "highlight": false
    }
  ],
  "published_at": "2026-10-15T03:20:00Z",
  "date_status": "in_period",
  "relevance": "direct",
  "score": 0.93,
  "explanation": "Пост о профилактическом рейде ГИБДД по безопасности пешеходов",
  "region": {
    "by_source": true,
    "by_content": true,
    "evidence": "Ачинск"
  },
  "sentiment": "neutral",
  "group_id": "g-1",
  "group_size": 3,
  "metrics": {
    "views": 5400,
    "likes": 31,
    "reposts": 4,
    "comments": null
  },
  "excluded": false,
  "found_by_target_id": "t-1"
}
```
</details>

## ResultPage

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `items` | [`Result`](#result)[] | да |  |
| `total` | integer | да |  |
| `has_more` | boolean | да |  |

## ResultGroup

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `group_id` | string | да |  |
| `title` | string | да |  |
| `size` | integer | да |  |
| `platforms` | [`Platform`](#platform)[] | да |  |
| `earliest_published_at` | string (date-time) \| null | да |  |
| `items` | [`Result`](#result)[] | да | Все размещения сюжета |

## GroupPage

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `items` | [`ResultGroup`](#resultgroup)[] | да |  |
| `total` | integer | да |  |
| `has_more` | boolean | да |  |

## ExclusionIn

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `result_ids` | string[] | да | мин. элементов 1 |
| `excluded` | boolean | да |  |
