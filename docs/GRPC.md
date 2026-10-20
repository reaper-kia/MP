# gRPC-контракты — справочник (сгенерирован из `contracts/**/*.proto`)

> Не править руками. Источник правды — `.proto`; после изменения: `make proto` (перегенерирует и этот файл).

Соглашения шаблона: первое поле каждого запроса — `common.v1.RequestContext context`; ошибки — gRPC status + `error-code` в trailing metadata (README §10); `optional` — поле может отсутствовать (в Python: `msg.HasField("x")`); `repeated` — список; enum с нулевым `*_UNSPECIFIED` = «не задано». Timestamp — `google.protobuf.Timestamp` (UTC).

## Содержание

- `common.v1` (`contracts/common/v1/common.proto`): 
- `common.v1` (`contracts/common/v1/platform.proto`): 
- `collector.v1` (`contracts/collector/v1/collector_service.proto`): [CollectorService](#collectorv1collectorservice)
- `ml.v1` (`contracts/ml/v1/ml_service.proto`): [MlService](#mlv1mlservice)
- `search.v1` (`contracts/search/v1/search_service.proto`): [SearchService](#searchv1searchservice)

# Пакет `common.v1` — `contracts/common/v1/common.proto`

<a id="commonv1requestcontext"></a>
### message `common.v1.RequestContext`

Контекст запроса. Заполняет ТОЛЬКО Gateway; первое поле каждого запроса. Авторизации в продукте нет (по ТЗ): используется request_id — сквозной id для логов. actor_* оставлены на будущее (если появятся пользователи) и сейчас пустые.

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `request_id` | string (str) |  |  |
| 2 | `actor_user_id` | string (str) |  |  |
| 3 | `actor_role` | string (str) |  | "user" / "admin" |

# Пакет `common.v1` — `contracts/common/v1/platform.proto`

<a id="commonv1platform"></a>
### enum `common.v1.Platform`

Площадки. Общий enum для collector, search и ml.

| Значение | № | Описание |
|---|---|---|
| `PLATFORM_UNSPECIFIED` | 0 |  |
| `PLATFORM_VK` | 1 |  |
| `PLATFORM_OK` | 2 |  |
| `PLATFORM_MAX` | 3 |  |
| `PLATFORM_NEWS` | 4 | Новостные сайты из перечня агентства (доп. возможность) |

<a id="commonv1period"></a>
### message `common.v1.Period`

Период по дате публикации. Обе границы включительно. Даты пользователь выбирает в часовом поясе Asia/Krasnoyarsk (UTC+7): start = 00:00:00 первого дня, end = 23:59:59.999999999 последнего дня, переведённые в UTC. Доли секунды в end обязательны: MAX и часть страниц отдают время с миллисекундами, и пост, опубликованный в последнюю секунду дня, иначе выпал бы из периода. (не from/to: from — ключевое слово Python, в сгенерированном коде неудобно)

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `start` | Timestamp |  |  |
| 2 | `end` | Timestamp |  |  |

<a id="commonv1errorinfo"></a>
### message `common.v1.ErrorInfo`

Ошибка конкретного источника/площадки внутри успешного в целом ответа.

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `code` | string (str) |  | Машинный код: PLATFORM_UNAVAILABLE, SOURCE_NOT_FOUND, SOURCE_PRIVATE, RATE_LIMITED, TIMEOUT, PARSE_ERROR, AUTH_REQUIRED, ML_UNAVAILABLE, INTERNAL |
| 2 | `message` | string (str) |  | Текст для пользователя, по-русски |

# Пакет `collector.v1` — `contracts/collector/v1/collector_service.proto`

<a id="collectorv1collectorservice"></a>
### service `collector.v1.CollectorService`

Получение публикаций с площадок. Владелец — B1. Своей БД нет. Возвращает ТОЛЬКО реально полученные с площадки посты: ссылка, текст и дата берутся из ответа площадки, ничего не генерируется.  Ошибки (gRPC status + error-code в trailing metadata, как в шаблоне): UNSUPPORTED_URL       INVALID_ARGUMENT     ссылка не похожа на группу/канал поддерживаемой площадки SOURCE_NOT_FOUND      NOT_FOUND            группы/канала не существует SOURCE_PRIVATE        FAILED_PRECONDITION  закрытая группа, контент недоступен PLATFORM_UNAVAILABLE  UNAVAILABLE          площадка/ключ недоступны RATE_LIMITED          RESOURCE_EXHAUSTED   упёрлись в лимит

| RPC | Запрос → ответ | Описание |
|---|---|---|
| `GetPlatforms` | [`GetPlatformsRequest`](#collectorv1getplatformsrequest) → [`GetPlatformsResponse`](#collectorv1getplatformsresponse) | Какие площадки и режимы сейчас доступны (для UI и для search_service) |
| `ResolveSource` | [`ResolveSourceRequest`](#collectorv1resolvesourcerequest) → [`ResolveSourceResponse`](#collectorv1resolvesourceresponse) | Ссылка от пользователя → нормализованная карточка источника |
| `CollectFromSource` | [`CollectFromSourceRequest`](#collectorv1collectfromsourcerequest) → [`CollectFromSourceResponse`](#collectorv1collectfromsourceresponse) | Режим «по выбранным источникам»: посты одного источника за период |
| `SearchPlatform` | [`SearchPlatformRequest`](#collectorv1searchplatformrequest) → [`SearchPlatformResponse`](#collectorv1searchplatformresponse) | Режим «без ограничения списком»: поиск по всей площадке |

<a id="collectorv1platformhealth"></a>
### enum `collector.v1.PlatformHealth`

| Значение | № | Описание |
|---|---|---|
| `PLATFORM_HEALTH_UNSPECIFIED` | 0 |  |
| `PLATFORM_HEALTH_OK` | 1 |  |
| `PLATFORM_HEALTH_DEGRADED` | 2 | работает частично (например, нет глобального поиска) |
| `PLATFORM_HEALTH_UNAVAILABLE` | 3 |  |

<a id="collectorv1platforminfo"></a>
### message `collector.v1.PlatformInfo`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `platform` | [`common.v1.Platform`](#commonv1platform) |  |  |
| 2 | `title` | string (str) |  |  |
| 3 | `source_mode_supported` | bool |  |  |
| 4 | `global_mode_supported` | bool |  |  |
| 5 | `health` | [`PlatformHealth`](#collectorv1platformhealth) |  |  |
| 6 | `note` | string (str) |  | Пояснение для пользователя: «глобальный поиск через Яндекс», «нет ключа API» и т.п. |

<a id="collectorv1getplatformsrequest"></a>
### message `collector.v1.GetPlatformsRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |

<a id="collectorv1getplatformsresponse"></a>
### message `collector.v1.GetPlatformsResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `platforms` | [`PlatformInfo`](#collectorv1platforminfo) | repeated |  |

<a id="collectorv1sourceinfo"></a>
### message `collector.v1.SourceInfo`

Источник: группа VK / группа OK / канал MAX / сайт

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `platform` | [`common.v1.Platform`](#commonv1platform) |  |  |
| 2 | `external_id` | string (str) |  | Стабильный id на площадке: VK owner_id (-123), OK gid, MAX channel id/handle, домен сайта |
| 3 | `screen_name` | string (str) |  | Короткое имя: vk.com/<screen_name>, max.ru/<handle> |
| 4 | `url` | string (str) |  | Каноничная ссылка на источник |
| 5 | `name` | string (str) |  |  |
| 6 | `city` | string (str) | optional |  |
| 7 | `members_count` | int64 (int) | optional |  |
| 8 | `is_closed` | bool |  |  |

<a id="collectorv1resolvesourcerequest"></a>
### message `collector.v1.ResolveSourceRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `url` | string (str) |  | Любая форма ссылки: vk.com/club1, https://vk.com/krsk_news, ok.ru/group/123, max.ru/handle |

<a id="collectorv1resolvesourceresponse"></a>
### message `collector.v1.ResolveSourceResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `source` | [`SourceInfo`](#collectorv1sourceinfo) |  |  |

<a id="collectorv1postmetrics"></a>
### message `collector.v1.PostMetrics`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `views` | int64 (int) | optional |  |
| 2 | `likes` | int64 (int) | optional |  |
| 3 | `reposts` | int64 (int) | optional |  |
| 4 | `comments` | int64 (int) | optional |  |

<a id="collectorv1rawpost"></a>
### message `collector.v1.RawPost`

Нормализованная публикация. Ключ уникальности: (platform, source_external_id, post_external_id).

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `platform` | [`common.v1.Platform`](#commonv1platform) |  |  |
| 2 | `source_external_id` | string (str) |  |  |
| 3 | `source_name` | string (str) |  |  |
| 4 | `source_url` | string (str) |  |  |
| 5 | `post_external_id` | string (str) |  |  |
| 6 | `url` | string (str) |  | Прямая каноничная ссылка на пост: https://vk.com/wall-123_456, https://ok.ru/group/1/topic/2 |
| 7 | `title` | string (str) | optional | Заголовок, если площадка его отдаёт (статья, сайт). Иначе пусто — заголовок из начала поста делает search. |
| 8 | `text` | string (str) |  | Полный текст поста как на площадке (без HTML). Для репоста — текст + текст оригинала. |
| 9 | `published_at` | Timestamp | optional | Нет даты — поле не заполняется. Никогда не подставлять «сейчас». |
| 10 | `metrics` | [`PostMetrics`](#collectorv1postmetrics) |  |  |
| 11 | `is_repost` | bool |  |  |
| 12 | `repost_of_url` | string (str) | optional |  |
| 13 | `fetched_at` | Timestamp |  |  |

<a id="collectorv1collectfromsourcerequest"></a>
### message `collector.v1.CollectFromSourceRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `platform` | [`common.v1.Platform`](#commonv1platform) |  |  |
| 3 | `source_external_id` | string (str) |  |  |
| 4 | `period` | [`common.v1.Period`](#commonv1period) |  |  |
| 5 | `keywords` | string (str) | repeated | Подсказка: если площадка умеет искать внутри источника (VK wall.search), можно сузить. Можно игнорировать и отдать все посты за период — отбор всё равно делает ML. |
| 6 | `max_posts` | uint32 (int ≥ 0) |  | Ограничение, чтобы не выкачивать годовой архив. 0 = по умолчанию (300). |

<a id="collectorv1collectfromsourceresponse"></a>
### message `collector.v1.CollectFromSourceResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `posts` | [`RawPost`](#collectorv1rawpost) | repeated |  |
| 2 | `truncated` | bool |  | true — упёрлись в max_posts, за период есть ещё |
| 3 | `warnings` | string (str) | repeated | Нефатальные проблемы: «у 3 постов нет даты», «часть страниц не загрузилась» |

<a id="collectorv1searchplatformrequest"></a>
### message `collector.v1.SearchPlatformRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `platform` | [`common.v1.Platform`](#commonv1platform) |  |  |
| 3 | `queries` | string (str) | repeated | Поисковые фразы от ML (AnalyzeQuery.search_queries). Каждая ищется отдельно, результаты объединяются. |
| 4 | `period` | [`common.v1.Period`](#commonv1period) |  |  |
| 5 | `region_terms` | string (str) | repeated | Подсказка: термины региона («Красноярск», «Красноярский край», «Норильск», ...). Как keywords, коннектор может её игнорировать и искать по фразам queries как есть: привязку к региону и отбор по смыслу делают ml_service и search_service. |
| 6 | `max_posts` | uint32 (int ≥ 0) |  | 0 = по умолчанию (500) |

<a id="collectorv1searchplatformresponse"></a>
### message `collector.v1.SearchPlatformResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `posts` | [`RawPost`](#collectorv1rawpost) | repeated |  |
| 2 | `truncated` | bool |  |  |
| 3 | `warnings` | string (str) | repeated |  |

# Пакет `ml.v1` — `contracts/ml/v1/ml_service.proto`

<a id="mlv1mlservice"></a>
### service `ml.v1.MlService`

Анализ текста. Владелец — ML. Своей БД нет. Никогда не меняет и не придумывает тексты постов: возвращает только оценки и позиции фрагментов внутри переданного текста.  Ошибки: ML_UNAVAILABLE (UNAVAILABLE) — LLM/эмбеддинги недоступны и фолбэк выключен.

| RPC | Запрос → ответ | Описание |
|---|---|---|
| `AnalyzeQuery` | [`AnalyzeQueryRequest`](#mlv1analyzequeryrequest) → [`AnalyzeQueryResponse`](#mlv1analyzequeryresponse) | Что хотел пользователь: тип запроса, поисковые фразы, сущности |
| `ScorePosts` | [`ScorePostsRequest`](#mlv1scorepostsrequest) → [`ScorePostsResponse`](#mlv1scorepostsresponse) | Связь постов с запросом. До 50 постов за вызов. |
| `GroupPosts` | [`GroupPostsRequest`](#mlv1grouppostsrequest) → [`GroupPostsResponse`](#mlv1grouppostsresponse) | Группировка одинаковых/пересказанных новостей в сюжеты |

<a id="mlv1querytype"></a>
### enum `ml.v1.QueryType`

| Значение | № | Описание |
|---|---|---|
| `QUERY_TYPE_UNSPECIFIED` | 0 |  |
| `QUERY_TYPE_TOPIC` | 1 | «Безопасность дорожного движения в Красноярском крае» |
| `QUERY_TYPE_EVENT` | 2 | «Открытие моста через Енисей 2026, Красноярск» |
| `QUERY_TYPE_PERSON` | 3 | «Губернатор ... — упоминания» |
| `QUERY_TYPE_NEWS_TEXT` | 4 | Вставлен текст исходной новости |

<a id="mlv1entitytype"></a>
### enum `ml.v1.EntityType`

| Значение | № | Описание |
|---|---|---|
| `ENTITY_TYPE_UNSPECIFIED` | 0 |  |
| `ENTITY_TYPE_PERSON` | 1 |  |
| `ENTITY_TYPE_ORGANIZATION` | 2 |  |
| `ENTITY_TYPE_LOCATION` | 3 |  |
| `ENTITY_TYPE_EVENT` | 4 |  |
| `ENTITY_TYPE_DATE` | 5 |  |
| `ENTITY_TYPE_NUMBER` | 6 |  |

<a id="mlv1entity"></a>
### message `ml.v1.Entity`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `text` | string (str) |  |  |
| 2 | `type` | [`EntityType`](#mlv1entitytype) |  |  |

<a id="mlv1queryanalysis"></a>
### message `ml.v1.QueryAnalysis`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `query_type` | [`QueryType`](#mlv1querytype) |  |  |
| 2 | `summary` | string (str) |  | Как система поняла запрос, одной фразой — показывается пользователю |
| 3 | `search_queries` | string (str) | repeated | 3–8 фраз для поиска по площадке (VK newsfeed.search, Яндекс site:ok.ru) |
| 4 | `entities` | [`Entity`](#mlv1entity) | repeated |  |
| 5 | `must_concepts` | string (str) | repeated | Без чего пост точно не подходит («дорожное движение», а не просто «безопасность») |
| 6 | `exclude_concepts` | string (str) | repeated | Что часто путают и надо отсекать («пожарная безопасность») |
| 7 | `needs_clarification` | bool |  | Запрос слишком общий/короткий — предложить уточнить |
| 8 | `clarification_hint` | string (str) |  |  |

<a id="mlv1analyzequeryrequest"></a>
### message `ml.v1.AnalyzeQueryRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `query` | string (str) |  |  |

<a id="mlv1analyzequeryresponse"></a>
### message `ml.v1.AnalyzeQueryResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `analysis` | [`QueryAnalysis`](#mlv1queryanalysis) |  |  |
| 2 | `degraded` | bool |  | true — LLM недоступна, ответ построен эвристикой |

<a id="mlv1relevance"></a>
### enum `ml.v1.Relevance`

| Значение | № | Описание |
|---|---|---|
| `RELEVANCE_UNSPECIFIED` | 0 |  |
| `RELEVANCE_DIRECT` | 1 | Прямо про тему/событие/человека; для NEWS_TEXT — та же новость (копия, сокращение, пересказ) |
| `RELEVANCE_INDIRECT` | 2 | Связано косвенно: упоминание вскользь, смежная тема |
| `RELEVANCE_DISPUTED` | 3 | Система не уверена — нужна проверка человеком |
| `RELEVANCE_IRRELEVANT` | 4 | Не подходит (в т.ч. похожая новость о другом событии). В подборку не идёт, но хранится. |

<a id="mlv1sentiment"></a>
### enum `ml.v1.Sentiment`

| Значение | № | Описание |
|---|---|---|
| `SENTIMENT_UNSPECIFIED` | 0 |  |
| `SENTIMENT_POSITIVE` | 1 |  |
| `SENTIMENT_NEUTRAL` | 2 |  |
| `SENTIMENT_NEGATIVE` | 3 |  |

<a id="mlv1textspan"></a>
### message `ml.v1.TextSpan`

Полуинтервал [start, end) в символах Python-строки text (code points).

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `start` | uint32 (int ≥ 0) |  |  |
| 2 | `end` | uint32 (int ≥ 0) |  |  |

<a id="mlv1postforscoring"></a>
### message `ml.v1.PostForScoring`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `id` | string (str) |  | id результата в search_service — вернуть как есть |
| 2 | `title` | string (str) | optional |  |
| 3 | `text` | string (str) |  |  |
| 4 | `source_name` | string (str) |  |  |
| 5 | `source_is_regional` | bool |  | Источник помечен как региональный в каталоге |

<a id="mlv1regionmatch"></a>
### message `ml.v1.RegionMatch`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `by_content` | bool |  | В тексте есть привязка к Красноярскому краю (город/район/организация края) |
| 2 | `evidence` | string (str) |  | Что именно нашли: «Ачинск», «Красноярская ГЭС». Пусто, если by_content = false. |

<a id="mlv1postscore"></a>
### message `ml.v1.PostScore`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `id` | string (str) |  |  |
| 2 | `relevance` | [`Relevance`](#mlv1relevance) |  |  |
| 3 | `score` | float |  | 0..1, для сортировки |
| 4 | `explanation` | string (str) |  | Почему так решили, 1 предложение по-русски: «Пост о рейде ГИБДД по пешеходным переходам в Ачинске» |
| 5 | `region` | [`RegionMatch`](#mlv1regionmatch) |  |  |
| 6 | `sentiment` | [`Sentiment`](#mlv1sentiment) |  |  |
| 7 | `excerpt_span` | [`TextSpan`](#mlv1textspan) |  | Самый релевантный фрагмент текста (для выдержки), ≤ 300 символов |
| 8 | `highlight_spans` | [`TextSpan`](#mlv1textspan) | repeated | Что подсветить (совпадающие сущности/фразы), позиции в text |

<a id="mlv1scorepostsrequest"></a>
### message `ml.v1.ScorePostsRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `query` | string (str) |  |  |
| 3 | `analysis` | [`QueryAnalysis`](#mlv1queryanalysis) |  |  |
| 4 | `posts` | [`PostForScoring`](#mlv1postforscoring) | repeated |  |

<a id="mlv1scorepostsresponse"></a>
### message `ml.v1.ScorePostsResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `scores` | [`PostScore`](#mlv1postscore) | repeated | По одному на каждый входной пост, в том же порядке |
| 2 | `degraded` | bool |  |  |

<a id="mlv1postforgrouping"></a>
### message `ml.v1.PostForGrouping`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `id` | string (str) |  |  |
| 2 | `title` | string (str) | optional |  |
| 3 | `text` | string (str) |  |  |

<a id="mlv1postgroup"></a>
### message `ml.v1.PostGroup`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `group_id` | string (str) |  |  |
| 2 | `post_ids` | string (str) | repeated |  |
| 3 | `representative_post_id` | string (str) |  | Пост, заголовок которого показываем у группы |

<a id="mlv1grouppostsrequest"></a>
### message `ml.v1.GroupPostsRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `posts` | [`PostForGrouping`](#mlv1postforgrouping) | repeated |  |

<a id="mlv1grouppostsresponse"></a>
### message `ml.v1.GroupPostsResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `groups` | [`PostGroup`](#mlv1postgroup) | repeated | Каждый входной пост ровно в одной группе (одиночки — группа из одного) |

# Пакет `search.v1` — `contracts/search/v1/search_service.proto`

<a id="searchv1searchservice"></a>
### service `search.v1.SearchService`

Ядро: источники, поисковые задачи, подборки, экспорт. Владелец — B2. Своя БД search_db. Ходит в collector_service и ml_service. HTTP-ручки gateway (contracts/http/openapi.yaml) один к одному мапятся на эти RPC.  Ошибки (error-code → HTTP): SOURCE_NOT_FOUND        NOT_FOUND            404 SOURCE_ALREADY_EXISTS   ALREADY_EXISTS       409 UNSUPPORTED_URL         INVALID_ARGUMENT     422  (проброс из collector) SEARCH_NOT_FOUND        NOT_FOUND            404 SEARCH_INVALID_PARAMS   INVALID_ARGUMENT     422  (пустой запрос, from > to, mode=selected без источников) SEARCH_NOT_FINISHED     FAILED_PRECONDITION  409  (retry у незавершённого) RESULT_NOT_FOUND        NOT_FOUND            404

| RPC | Запрос → ответ | Описание |
|---|---|---|
| `ResolveSource` | [`ResolveSourceRequest`](#searchv1resolvesourcerequest) → [`ResolveSourceResponse`](#searchv1resolvesourceresponse) | ── источники ── |
| `CreateSource` | [`CreateSourceRequest`](#searchv1createsourcerequest) → [`CreateSourceResponse`](#searchv1createsourceresponse) |  |
| `ListSources` | [`ListSourcesRequest`](#searchv1listsourcesrequest) → [`ListSourcesResponse`](#searchv1listsourcesresponse) |  |
| `UpdateSource` | [`UpdateSourceRequest`](#searchv1updatesourcerequest) → [`UpdateSourceResponse`](#searchv1updatesourceresponse) |  |
| `DeleteSource` | [`DeleteSourceRequest`](#searchv1deletesourcerequest) → [`DeleteSourceResponse`](#searchv1deletesourceresponse) |  |
| `ImportSources` | [`ImportSourcesRequest`](#searchv1importsourcesrequest) → [`ImportSourcesResponse`](#searchv1importsourcesresponse) |  |
| `StartSearch` | [`StartSearchRequest`](#searchv1startsearchrequest) → [`StartSearchResponse`](#searchv1startsearchresponse) | ── поиск ── Создаёт задачу и сразу возвращает её (status=QUEUED). Выполнение — в фоне внутри search_service. Тот же поиск недавно уже был (B2-20) — сразу копия готовой подборки: финальный статус и cache. |
| `GetSearch` | [`GetSearchRequest`](#searchv1getsearchrequest) → [`GetSearchResponse`](#searchv1getsearchresponse) |  |
| `ListSearches` | [`ListSearchesRequest`](#searchv1listsearchesrequest) → [`ListSearchesResponse`](#searchv1listsearchesresponse) |  |
| `RetrySearch` | [`RetrySearchRequest`](#searchv1retrysearchrequest) → [`RetrySearchResponse`](#searchv1retrysearchresponse) | Повторить упавшие цели (или указанные). Уже найденное сохраняется. |
| `CancelSearch` | [`CancelSearchRequest`](#searchv1cancelsearchrequest) → [`CancelSearchResponse`](#searchv1cancelsearchresponse) | Для уже завершённого поиска (completed/partial/failed/cancelled) ничего не меняет: отвечает текущим состоянием, без ошибки. |
| `ListResults` | [`ListResultsRequest`](#searchv1listresultsrequest) → [`ListResultsResponse`](#searchv1listresultsresponse) | ── подборка ── |
| `ListGroups` | [`ListGroupsRequest`](#searchv1listgroupsrequest) → [`ListGroupsResponse`](#searchv1listgroupsresponse) |  |
| `SetExcluded` | [`SetExcludedRequest`](#searchv1setexcludedrequest) → [`SetExcludedResponse`](#searchv1setexcludedresponse) |  |
| `ExportSearch` | [`ExportSearchRequest`](#searchv1exportsearchrequest) → [`ExportSearchResponse`](#searchv1exportsearchresponse) |  |

<a id="searchv1source"></a>
### message `search.v1.Source`

───────────────────────── источники ─────────────────────────

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `id` | string (str) |  |  |
| 2 | `platform` | [`common.v1.Platform`](#commonv1platform) |  |  |
| 3 | `external_id` | string (str) |  |  |
| 4 | `url` | string (str) |  |  |
| 5 | `name` | string (str) |  |  |
| 6 | `city` | string (str) | optional |  |
| 7 | `is_regional` | bool |  | Источник относится к Красноярскому краю (регион по источнику) |
| 8 | `is_active` | bool |  | Участвует в поиске «без ограничения списком» и предлагается по умолчанию |
| 9 | `notes` | string (str) |  |  |
| 10 | `created_at` | Timestamp |  |  |
| 11 | `updated_at` | Timestamp |  |  |

<a id="searchv1sourcepreview"></a>
### message `search.v1.SourcePreview`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `platform` | [`common.v1.Platform`](#commonv1platform) |  |  |
| 2 | `external_id` | string (str) |  |  |
| 3 | `url` | string (str) |  |  |
| 4 | `name` | string (str) |  |  |
| 5 | `city` | string (str) | optional |  |
| 6 | `members_count` | int64 (int) | optional |  |
| 7 | `existing_source_id` | string (str) | optional | Такой источник уже есть в каталоге |

<a id="searchv1resolvesourcerequest"></a>
### message `search.v1.ResolveSourceRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `url` | string (str) |  |  |

<a id="searchv1resolvesourceresponse"></a>
### message `search.v1.ResolveSourceResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `preview` | [`SourcePreview`](#searchv1sourcepreview) |  |  |

<a id="searchv1createsourcerequest"></a>
### message `search.v1.CreateSourceRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `url` | string (str) |  |  |
| 3 | `name` | string (str) | optional | Пусто — взять название с площадки |
| 4 | `is_regional` | bool |  |  |
| 5 | `notes` | string (str) |  |  |

<a id="searchv1createsourceresponse"></a>
### message `search.v1.CreateSourceResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `source` | [`Source`](#searchv1source) |  |  |

<a id="searchv1listsourcesrequest"></a>
### message `search.v1.ListSourcesRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `platforms` | [`common.v1.Platform`](#commonv1platform) | repeated | Пусто — все площадки |
| 3 | `q` | string (str) |  | Поиск по названию/ссылке |
| 4 | `is_active` | bool | optional |  |
| 5 | `limit` | uint32 (int ≥ 0) |  |  |
| 6 | `offset` | uint32 (int ≥ 0) |  |  |

<a id="searchv1listsourcesresponse"></a>
### message `search.v1.ListSourcesResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `sources` | [`Source`](#searchv1source) | repeated |  |
| 2 | `total` | uint32 (int ≥ 0) |  |  |
| 3 | `has_more` | bool |  |  |

<a id="searchv1updatesourcerequest"></a>
### message `search.v1.UpdateSourceRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `source_id` | string (str) |  |  |
| 3 | `name` | string (str) | optional |  |
| 4 | `is_regional` | bool | optional |  |
| 5 | `is_active` | bool | optional |  |
| 6 | `notes` | string (str) | optional |  |

<a id="searchv1updatesourceresponse"></a>
### message `search.v1.UpdateSourceResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `source` | [`Source`](#searchv1source) |  |  |

<a id="searchv1deletesourcerequest"></a>
### message `search.v1.DeleteSourceRequest`

Мягкое удаление: история поисков хранит снимок источника

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `source_id` | string (str) |  |  |

<a id="searchv1deletesourceresponse"></a>
### message `search.v1.DeleteSourceResponse`

_Пустое сообщение._

<a id="searchv1importsourcesrequest"></a>
### message `search.v1.ImportSourcesRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `xlsx` | bytes |  | Содержимое .xlsx: колонка A — ссылка, B — название (необяз.), C — «региональный» да/нет (необяз.) |

<a id="searchv1importrowerror"></a>
### message `search.v1.ImportRowError`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `row` | uint32 (int ≥ 0) |  |  |
| 2 | `value` | string (str) |  |  |
| 3 | `error` | [`common.v1.ErrorInfo`](#commonv1errorinfo) |  |  |

<a id="searchv1importsourcesresponse"></a>
### message `search.v1.ImportSourcesResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `created` | uint32 (int ≥ 0) |  |  |
| 2 | `duplicates` | uint32 (int ≥ 0) |  |  |
| 3 | `failed` | [`ImportRowError`](#searchv1importrowerror) | repeated |  |

<a id="searchv1searchmode"></a>
### enum `search.v1.SearchMode`

───────────────────────── поиск ─────────────────────────

| Значение | № | Описание |
|---|---|---|
| `SEARCH_MODE_UNSPECIFIED` | 0 |  |
| `SEARCH_MODE_SELECTED` | 1 | Только по выбранным источникам |
| `SEARCH_MODE_GLOBAL` | 2 | По всей площадке + все активные источники каталога |

<a id="searchv1searchstatus"></a>
### enum `search.v1.SearchStatus`

| Значение | № | Описание |
|---|---|---|
| `SEARCH_STATUS_UNSPECIFIED` | 0 |  |
| `SEARCH_STATUS_QUEUED` | 1 |  |
| `SEARCH_STATUS_RUNNING` | 2 |  |
| `SEARCH_STATUS_COMPLETED` | 3 | Все цели обработаны (результатов может быть 0 — это «ничего не найдено», а не ошибка) |
| `SEARCH_STATUS_PARTIAL` | 4 | Завершён, но часть целей упала — найденное сохранено |
| `SEARCH_STATUS_FAILED` | 5 | Упали все цели или системная ошибка |
| `SEARCH_STATUS_CANCELLED` | 6 |  |

<a id="searchv1searchstage"></a>
### enum `search.v1.SearchStage`

| Значение | № | Описание |
|---|---|---|
| `SEARCH_STAGE_UNSPECIFIED` | 0 |  |
| `SEARCH_STAGE_QUEUED` | 1 |  |
| `SEARCH_STAGE_ANALYZING_QUERY` | 2 |  |
| `SEARCH_STAGE_COLLECTING` | 3 |  |
| `SEARCH_STAGE_SCORING` | 4 |  |
| `SEARCH_STAGE_GROUPING` | 5 |  |
| `SEARCH_STAGE_DONE` | 6 |  |

<a id="searchv1querytype"></a>
### enum `search.v1.QueryType`

| Значение | № | Описание |
|---|---|---|
| `QUERY_TYPE_UNSPECIFIED` | 0 |  |
| `QUERY_TYPE_TOPIC` | 1 |  |
| `QUERY_TYPE_EVENT` | 2 |  |
| `QUERY_TYPE_PERSON` | 3 |  |
| `QUERY_TYPE_NEWS_TEXT` | 4 |  |

<a id="searchv1searchparams"></a>
### message `search.v1.SearchParams`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `query` | string (str) |  |  |
| 2 | `query_type` | [`QueryType`](#searchv1querytype) |  |  |
| 3 | `period_from` | string (str) |  | Даты YYYY-MM-DD в Asia/Krasnoyarsk, включительно |
| 4 | `period_to` | string (str) |  |  |
| 5 | `mode` | [`SearchMode`](#searchv1searchmode) |  |  |
| 6 | `platforms` | [`common.v1.Platform`](#commonv1platform) | repeated |  |
| 7 | `source_ids` | string (str) | repeated | Для SELECTED — выбранные; для GLOBAL — пусто |

<a id="searchv1targetkind"></a>
### enum `search.v1.TargetKind`

| Значение | № | Описание |
|---|---|---|
| `TARGET_KIND_UNSPECIFIED` | 0 |  |
| `TARGET_KIND_SOURCE` | 1 | Конкретный источник (CollectFromSource) |
| `TARGET_KIND_PLATFORM_SEARCH` | 2 | Поиск по всей площадке (SearchPlatform) |

<a id="searchv1targetstatus"></a>
### enum `search.v1.TargetStatus`

| Значение | № | Описание |
|---|---|---|
| `TARGET_STATUS_UNSPECIFIED` | 0 |  |
| `TARGET_STATUS_PENDING` | 1 |  |
| `TARGET_STATUS_RUNNING` | 2 |  |
| `TARGET_STATUS_DONE` | 3 | Обработан, есть посты за период |
| `TARGET_STATUS_EMPTY` | 4 | Обработан, постов за период нет |
| `TARGET_STATUS_FAILED` | 5 |  |
| `TARGET_STATUS_SKIPPED` | 6 | Пропущен (площадка выключена, поиск отменён) |

<a id="searchv1searchtarget"></a>
### message `search.v1.SearchTarget`

Где искали: одна строка в блоке «Охват поиска»

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `id` | string (str) |  |  |
| 2 | `kind` | [`TargetKind`](#searchv1targetkind) |  |  |
| 3 | `platform` | [`common.v1.Platform`](#commonv1platform) |  |  |
| 4 | `source_id` | string (str) | optional | Для SOURCE; пусто для PLATFORM_SEARCH |
| 5 | `name` | string (str) |  | Снимок названия на момент поиска: «Новости Красноярска» / «Поиск по всему VK» |
| 6 | `url` | string (str) | optional |  |
| 7 | `status` | [`TargetStatus`](#searchv1targetstatus) |  |  |
| 8 | `fetched` | uint32 (int ≥ 0) |  | Сколько постов получено за период |
| 9 | `matched` | uint32 (int ≥ 0) |  | Сколько из них попало в подборку (direct+indirect+disputed) |
| 10 | `error` | [`common.v1.ErrorInfo`](#commonv1errorinfo) | optional |  |
| 11 | `attempts` | uint32 (int ≥ 0) |  |  |
| 12 | `finished_at` | Timestamp | optional |  |

<a id="searchv1searchcounts"></a>
### message `search.v1.SearchCounts`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `total` | uint32 (int ≥ 0) |  | В подборке: direct + indirect + disputed, без исключённых |
| 2 | `direct` | uint32 (int ≥ 0) |  |  |
| 3 | `indirect` | uint32 (int ≥ 0) |  |  |
| 4 | `disputed` | uint32 (int ≥ 0) |  |  |
| 5 | `rejected` | uint32 (int ≥ 0) |  | Отсеяны системой как нерелевантные (не в total) |
| 6 | `excluded` | uint32 (int ≥ 0) |  | Исключены пользователем (не в total) |
| 7 | `unknown_date` | uint32 (int ≥ 0) |  | Из total — без даты публикации |
| 8 | `groups` | uint32 (int ≥ 0) |  | Сюжетов (групп) среди total |

<a id="searchv1searchprogress"></a>
### message `search.v1.SearchProgress`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `targets_total` | uint32 (int ≥ 0) |  |  |
| 2 | `targets_finished` | uint32 (int ≥ 0) |  |  |
| 3 | `percent` | uint32 (int ≥ 0) |  | 0..100 |

<a id="searchv1queryanalysisview"></a>
### message `search.v1.QueryAnalysisView`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `query_type` | [`QueryType`](#searchv1querytype) |  |  |
| 2 | `summary` | string (str) |  |  |
| 3 | `search_queries` | string (str) | repeated |  |
| 4 | `needs_clarification` | bool |  |  |
| 5 | `clarification_hint` | string (str) |  |  |

<a id="searchv1search"></a>
### message `search.v1.Search`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `id` | string (str) |  |  |
| 2 | `status` | [`SearchStatus`](#searchv1searchstatus) |  |  |
| 3 | `stage` | [`SearchStage`](#searchv1searchstage) |  |  |
| 4 | `progress` | [`SearchProgress`](#searchv1searchprogress) |  |  |
| 5 | `params` | [`SearchParams`](#searchv1searchparams) |  |  |
| 6 | `query_analysis` | [`QueryAnalysisView`](#searchv1queryanalysisview) | optional |  |
| 7 | `targets` | [`SearchTarget`](#searchv1searchtarget) | repeated |  |
| 8 | `counts` | [`SearchCounts`](#searchv1searchcounts) |  |  |
| 9 | `warnings` | string (str) | repeated | «ML работал в упрощённом режиме», «у VK обрезано до 300 постов на источник» |
| 10 | `created_at` | Timestamp |  |  |
| 11 | `started_at` | Timestamp | optional |  |
| 12 | `finished_at` | Timestamp | optional |  |
| 13 | `cache` | [`SearchCacheInfo`](#searchv1searchcacheinfo) | optional | Подборка из кэша (B2-20): копия готового поиска с теми же параметрами. Нет — настоящий поиск |

<a id="searchv1searchcacheinfo"></a>
### message `search.v1.SearchCacheInfo`

Откуда взята подборка из кэша

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `from_search_id` | string (str) |  | исходный поиск, с которого снята копия |
| 2 | `created_at` | Timestamp |  | когда исходный поиск завершился — «собрана N мин назад» |

<a id="searchv1startsearchrequest"></a>
### message `search.v1.StartSearchRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `query` | string (str) |  |  |
| 3 | `period_from` | string (str) |  |  |
| 4 | `period_to` | string (str) |  |  |
| 5 | `mode` | [`SearchMode`](#searchv1searchmode) |  |  |
| 6 | `platforms` | [`common.v1.Platform`](#commonv1platform) | repeated | GLOBAL — площадки, по которым ищем. SELECTED — игнорируется: площадки берутся из source_ids. |
| 7 | `source_ids` | string (str) | repeated |  |
| 8 | `fresh` | bool |  | true — не брать готовую подборку из кэша, искать заново («Обновить», «Повторить»), B2-20 |

<a id="searchv1startsearchresponse"></a>
### message `search.v1.StartSearchResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `search` | [`Search`](#searchv1search) |  |  |

<a id="searchv1getsearchrequest"></a>
### message `search.v1.GetSearchRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `search_id` | string (str) |  |  |

<a id="searchv1getsearchresponse"></a>
### message `search.v1.GetSearchResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `search` | [`Search`](#searchv1search) |  |  |

<a id="searchv1listsearchesrequest"></a>
### message `search.v1.ListSearchesRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `limit` | uint32 (int ≥ 0) |  |  |
| 3 | `offset` | uint32 (int ≥ 0) |  |  |

<a id="searchv1listsearchesresponse"></a>
### message `search.v1.ListSearchesResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `searches` | [`Search`](#searchv1search) | repeated | targets в списке не заполняются |
| 2 | `has_more` | bool |  |  |

<a id="searchv1retrysearchrequest"></a>
### message `search.v1.RetrySearchRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `search_id` | string (str) |  |  |
| 3 | `target_ids` | string (str) | repeated | Пусто — все FAILED цели |

<a id="searchv1retrysearchresponse"></a>
### message `search.v1.RetrySearchResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `search` | [`Search`](#searchv1search) |  |  |

<a id="searchv1cancelsearchrequest"></a>
### message `search.v1.CancelSearchRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `search_id` | string (str) |  |  |

<a id="searchv1cancelsearchresponse"></a>
### message `search.v1.CancelSearchResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `search` | [`Search`](#searchv1search) |  |  |

<a id="searchv1relevance"></a>
### enum `search.v1.Relevance`

───────────────────────── подборка ─────────────────────────

| Значение | № | Описание |
|---|---|---|
| `RELEVANCE_UNSPECIFIED` | 0 |  |
| `RELEVANCE_DIRECT` | 1 |  |
| `RELEVANCE_INDIRECT` | 2 |  |
| `RELEVANCE_DISPUTED` | 3 |  |
| `RELEVANCE_IRRELEVANT` | 4 |  |

<a id="searchv1sentiment"></a>
### enum `search.v1.Sentiment`

| Значение | № | Описание |
|---|---|---|
| `SENTIMENT_UNSPECIFIED` | 0 |  |
| `SENTIMENT_POSITIVE` | 1 |  |
| `SENTIMENT_NEUTRAL` | 2 |  |
| `SENTIMENT_NEGATIVE` | 3 |  |

<a id="searchv1titlesource"></a>
### enum `search.v1.TitleSource`

| Значение | № | Описание |
|---|---|---|
| `TITLE_SOURCE_UNSPECIFIED` | 0 |  |
| `TITLE_SOURCE_TITLE` | 1 | Заголовок с площадки |
| `TITLE_SOURCE_POST_START` | 2 | Заголовка нет — первые ~120 символов поста |

<a id="searchv1datestatus"></a>
### enum `search.v1.DateStatus`

| Значение | № | Описание |
|---|---|---|
| `DATE_STATUS_UNSPECIFIED` | 0 |  |
| `DATE_STATUS_IN_PERIOD` | 1 |  |
| `DATE_STATUS_UNKNOWN` | 2 | Площадка не отдала дату — нельзя утверждать, что пост в периоде |

<a id="searchv1resultsort"></a>
### enum `search.v1.ResultSort`

| Значение | № | Описание |
|---|---|---|
| `RESULT_SORT_UNSPECIFIED` | 0 |  |
| `RESULT_SORT_RELEVANCE` | 1 | по умолчанию: direct → indirect → disputed, внутри по score |
| `RESULT_SORT_DATE_DESC` | 2 |  |
| `RESULT_SORT_DATE_ASC` | 3 |  |

<a id="searchv1resultsourceref"></a>
### message `search.v1.ResultSourceRef`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `source_id` | string (str) | optional |  |
| 2 | `name` | string (str) |  |  |
| 3 | `url` | string (str) |  |  |
| 4 | `is_regional` | bool |  |  |

<a id="searchv1excerptpart"></a>
### message `search.v1.ExcerptPart`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `text` | string (str) |  |  |
| 2 | `highlight` | bool |  |  |

<a id="searchv1resultregion"></a>
### message `search.v1.ResultRegion`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `by_source` | bool |  |  |
| 2 | `by_content` | bool |  |  |
| 3 | `evidence` | string (str) |  |  |

<a id="searchv1resultmetrics"></a>
### message `search.v1.ResultMetrics`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `views` | int64 (int) | optional |  |
| 2 | `likes` | int64 (int) | optional |  |
| 3 | `reposts` | int64 (int) | optional |  |
| 4 | `comments` | int64 (int) | optional |  |

<a id="searchv1result"></a>
### message `search.v1.Result`

Публикация в контексте конкретного поиска

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `id` | string (str) |  |  |
| 2 | `publication_id` | string (str) |  | Глобальный id публикации (одинаков в разных поисках) |
| 3 | `platform` | [`common.v1.Platform`](#commonv1platform) |  |  |
| 4 | `source` | [`ResultSourceRef`](#searchv1resultsourceref) |  |  |
| 5 | `url` | string (str) |  |  |
| 6 | `title` | string (str) |  |  |
| 7 | `title_source` | [`TitleSource`](#searchv1titlesource) |  |  |
| 8 | `excerpt` | string (str) |  | Дословный фрагмент исходного текста, ≤ 300 символов |
| 9 | `excerpt_parts` | [`ExcerptPart`](#searchv1excerptpart) | repeated | Тот же excerpt, порезанный на куски для подсветки |
| 10 | `published_at` | Timestamp | optional |  |
| 11 | `date_status` | [`DateStatus`](#searchv1datestatus) |  |  |
| 12 | `relevance` | [`Relevance`](#searchv1relevance) |  |  |
| 13 | `score` | float |  |  |
| 14 | `explanation` | string (str) |  |  |
| 15 | `region` | [`ResultRegion`](#searchv1resultregion) |  |  |
| 16 | `sentiment` | [`Sentiment`](#searchv1sentiment) |  |  |
| 17 | `group_id` | string (str) | optional |  |
| 18 | `group_size` | uint32 (int ≥ 0) |  |  |
| 19 | `metrics` | [`ResultMetrics`](#searchv1resultmetrics) |  |  |
| 20 | `excluded` | bool |  |  |
| 21 | `found_by_target_id` | string (str) |  | Какая цель первой нашла пост |

<a id="searchv1resultfilter"></a>
### message `search.v1.ResultFilter`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `relevance` | [`Relevance`](#searchv1relevance) | repeated | Пусто = DIRECT+INDIRECT+DISPUTED. IRRELEVANT — только если явно запросили («отсеянные»). |
| 2 | `platforms` | [`common.v1.Platform`](#commonv1platform) | repeated |  |
| 3 | `target_ids` | string (str) | repeated |  |
| 4 | `date_status` | [`DateStatus`](#searchv1datestatus) | repeated | Пусто = любые |
| 5 | `include_excluded` | bool |  |  |

<a id="searchv1listresultsrequest"></a>
### message `search.v1.ListResultsRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `search_id` | string (str) |  |  |
| 3 | `filter` | [`ResultFilter`](#searchv1resultfilter) |  |  |
| 4 | `sort` | [`ResultSort`](#searchv1resultsort) |  |  |
| 5 | `limit` | uint32 (int ≥ 0) |  |  |
| 6 | `offset` | uint32 (int ≥ 0) |  |  |

<a id="searchv1listresultsresponse"></a>
### message `search.v1.ListResultsResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `results` | [`Result`](#searchv1result) | repeated |  |
| 2 | `total` | uint32 (int ≥ 0) |  |  |
| 3 | `has_more` | bool |  |  |

<a id="searchv1resultgroup"></a>
### message `search.v1.ResultGroup`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `group_id` | string (str) |  |  |
| 2 | `title` | string (str) |  |  |
| 3 | `size` | uint32 (int ≥ 0) |  |  |
| 4 | `platforms` | [`common.v1.Platform`](#commonv1platform) | repeated |  |
| 5 | `earliest_published_at` | Timestamp | optional |  |
| 6 | `results` | [`Result`](#searchv1result) | repeated | ВСЕ размещения группы — у каждого своя ссылка |

<a id="searchv1listgroupsrequest"></a>
### message `search.v1.ListGroupsRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `search_id` | string (str) |  |  |
| 3 | `filter` | [`ResultFilter`](#searchv1resultfilter) |  |  |
| 4 | `limit` | uint32 (int ≥ 0) |  |  |
| 5 | `offset` | uint32 (int ≥ 0) |  |  |

<a id="searchv1listgroupsresponse"></a>
### message `search.v1.ListGroupsResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `groups` | [`ResultGroup`](#searchv1resultgroup) | repeated |  |
| 2 | `total` | uint32 (int ≥ 0) |  |  |
| 3 | `has_more` | bool |  |  |

<a id="searchv1setexcludedrequest"></a>
### message `search.v1.SetExcludedRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `search_id` | string (str) |  |  |
| 3 | `result_ids` | string (str) | repeated |  |
| 4 | `excluded` | bool |  |  |

<a id="searchv1setexcludedresponse"></a>
### message `search.v1.SetExcludedResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `counts` | [`SearchCounts`](#searchv1searchcounts) |  | Пересчитанные счётчики |

<a id="searchv1exportformat"></a>
### enum `search.v1.ExportFormat`

| Значение | № | Описание |
|---|---|---|
| `EXPORT_FORMAT_UNSPECIFIED` | 0 |  |
| `EXPORT_FORMAT_XLSX` | 1 |  |
| `EXPORT_FORMAT_DOCX` | 2 |  |

<a id="searchv1exportsearchrequest"></a>
### message `search.v1.ExportSearchRequest`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `context` | [`common.v1.RequestContext`](#commonv1requestcontext) |  |  |
| 2 | `search_id` | string (str) |  |  |
| 3 | `format` | [`ExportFormat`](#searchv1exportformat) |  |  |
| 4 | `filter` | [`ResultFilter`](#searchv1resultfilter) |  | Тот же фильтр и сортировка, что сейчас на экране — файл совпадает с подборкой |
| 5 | `sort` | [`ResultSort`](#searchv1resultsort) |  |  |

<a id="searchv1exportsearchresponse"></a>
### message `search.v1.ExportSearchResponse`

| № | Поле | Тип | Метка | Описание |
|---|---|---|---|---|
| 1 | `content` | bytes |  |  |
| 2 | `filename` | string (str) |  | «podborka_2026-10-19_bdd.xlsx» |
| 3 | `mime_type` | string (str) |  |  |
