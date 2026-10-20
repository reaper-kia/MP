# Медиамониторинг соцсетей — архитектура и правила

Документ — единый источник правды для команды. Задачи по людям: [`docs/tasks/`](tasks/).
Контракты: HTTP для фронта — [`contracts/http/openapi.yaml`](../contracts/http/openapi.yaml)
(читать удобнее в [`API.md`](API.md)), gRPC между сервисами — `contracts/{collector,search,ml}/v1/*.proto`,
общие типы — `contracts/common/v1/platform.proto` (читать в [`GRPC.md`](GRPC.md)).

## 1. Что строим (одной фразой)

Сотрудник агентства вводит **одним полем** тему / событие / человека / текст новости, выбирает период и
режим («по моим источникам» / «везде»), жмёт «Найти», видит подборку **реально существующих** публикаций
VK / OK / MAX с прямыми ссылками, выдержками, объяснением «почему попало», проверяет спорные, исключает
лишнее и выгружает **XLSX**, в котором ровно то, что на экране.

Форма: **веб-приложение + расширение Chrome / Яндекс Браузера (MV3) «Проверить пост»**: выделенный
текст → поиск размещений в фоне → заголовки со ссылками в окошке; на странице группы — «Добавить в
источники». Ставится без прав администратора («Загрузить распакованное»), сервер — наш.

## 2. Схема

```
                      ┌────────────── Браузер ───────────────┐
                      │  Веб-UI (React)  │  Расширение MV3   │
                      └────────┬─────────┴─────────┬─────────┘
                               │ HTTP /api/v1 (openapi.yaml)
                      ┌────────▼─────────┐
                      │ gateway (TL)     │ FastAPI, без логики: HTTP ⇄ gRPC, ошибки, файлы
                      └────────┬─────────┘
                               │ gRPC
                      ┌────────▼─────────┐        ┌──────────────────┐
                      │ search_service   │──gRPC─▶│ ml_service (ML)  │ YandexGPT / Ollama,
                      │ (B2) — ядро      │        │ без БД           │ эмбеддинги, эвристики
                      │ источники, поиски│        └──────────────────┘
                      │ дедуп, экспорт   │        ┌──────────────────┐
                      │ фоновый пайплайн │──gRPC─▶│ collector_service│ VK API, OK, MAX, RSS,
                      └────────┬─────────┘        │ (B1) — без БД    │ Yandex Search API
                               │                  └──────────────────┘
                        ┌──────▼──────┐
                        │ search_db   │ Postgres
                        └─────────────┘
```

Это ровно то, что проверяет критерий «Архитектура»: **получение** (collector) · **отбор** (ml) ·
**хранение и обработка** (search) · **интерфейс** (frontend) — разделены.

| Сервис | Владелец | Порт gRPC | БД | Состояние (20.10, подробно — [`STATUS.md`](STATUS.md)) |
|---|---|---|---|---|
| search_service | B2 | 50053 | search_db :5435 | каталог, поиски, пайплайн, учёт, XLSX / DOCX, импорт |
| collector_service | B1 | 50054 | — | VK (API), OK (публичные страницы), новостные сайты (RSS) — вживую; MAX (Bot API) и Yandex Search — код и тесты, без ключей |
| ml_service | ML | 50055 (+ HTTP `/health` 8085) | — | Ollama `qwen2.5:7b-instruct` + `bge-m3`; цепочка `ollama,yandex` с эвристиками в конце |
| gateway | TL | 8000 (HTTP) | — | все 17 ручек `openapi.yaml`; авторизации нет (по ТЗ) |

## 3. Как проходит поиск (пайплайн в search_service)

`POST /api/v1/searches` → gateway → `SearchService.StartSearch` → запись `searches(status=queued)` →
ответ сразу. Пайплайн идёт **фоновой asyncio-задачей** внутри search_service, прогресс пишется в БД,
фронт опрашивает `GET /searches/{id}` раз в 1.5 с.

1. **analyzing_query** — `ml.AnalyzeQuery(query)` → тип запроса, 3–8 поисковых фраз, сущности,
   must/exclude-концепты. ML недоступен → фолбэк: фразы = сам запрос, `warnings += "упрощённый режим"`.
2. **Цели (targets)** — снимок на момент запуска (названия/ссылки копируются, правка каталога потом
   историю не меняет):
   - `selected`: по одной цели `source` на каждый выбранный источник выбранных площадок;
   - `global`: цель `source` на каждый **активный** источник каталога выбранных площадок
     + цель `platform_search` на каждую площадку с `global_mode=true` в `GetPlatforms` (сейчас —
     новостные сайты; VK / OK — только с ключом Yandex Search API). Collector не ответил — только
     каталог; нечего искать — 422 с понятным текстом.
3. **collecting** — параллельно (semaphore 5, таймаут 30–60 с на цель):
   `collector.CollectFromSource` / `collector.SearchPlatform`. Каждая цель получает свой статус:
   `done` / `empty` / `failed(error)`. Падение одной цели не роняет поиск.
4. **Сохранение и дедуп** — upsert в `publications` по ключу `(platform, source_external_id,
   post_external_id)`; связь `search_results(search_id, publication_id)` уникальна. Тот же пост,
   найденный двумя целями или двумя фразами, — **одна** запись (`found_by_target_id` = первая цель).
5. **Период** — `published_at` в периоде → `date_status=in_period`; вне периода → отбрасываем;
   даты нет → оставляем с `date_status=unknown` (UI: «дата недоступна», не утверждаем, что в периоде).
6. **scoring** — конвейером: посты каждой цели уходят на оценку сразу после её сбора (подборка растёт
   во время поиска); `ml.ScorePosts` батчами по 20–50 → relevance (`direct/indirect/disputed/irrelevant`),
   score, explanation, регион по тексту, тональность, позиция выдержки. `irrelevant` хранится
   (вкладка «Отсеяно системой» — пользователь может проверить, что ничего важного не потерялось).
7. **grouping** — `ml.GroupPosts` по прошедшим отбор → `group_id`. Группа — только для удобства
   просмотра: в счётчике каждое размещение отдельно, внутри группы все ссылки.
8. **Финал** — `completed` (все цели обработаны), `partial` (часть `failed`), `failed` (упали все
   или системная ошибка). `RetrySearch` перезапускает только упавшие цели и доливает результаты.

При рестарте search_service поиски в `running` помечаются `failed` с warning «прерван перезапуском».

## 4. Модель данных (search_db)

```
sources            id, platform, external_id, screen_name, url, name, city?, is_regional,
                   is_active, notes, deleted_at?, created_at, updated_at
                   UNIQUE(platform, external_id) WHERE deleted_at IS NULL

searches           id, query, query_type?, period_from, period_to, mode, platforms[],
                   source_ids[], query_analysis jsonb?, status, stage, warnings jsonb,
                   created_at, started_at?, finished_at?

search_targets     id, search_id→searches, kind, platform, source_id?, name, url?,
                   status, fetched, matched, error_code?, error_message?, attempts,
                   started_at?, finished_at?

publications       id, platform, source_external_id, post_external_id, url,
                   source_name, source_url, title?, text, published_at?, metrics jsonb,
                   is_repost, repost_of_url?, first_seen_at, last_seen_at
                   UNIQUE(platform, source_external_id, post_external_id)

search_results     id, search_id→searches, publication_id→publications, target_id→search_targets,
                   relevance, score, explanation, region_by_source, region_by_content,
                   region_evidence, sentiment?, excerpt_start, excerpt_end, highlights jsonb,
                   group_id?, date_status, excluded, excluded_at?
                   UNIQUE(search_id, publication_id)
```

Счётчики (`counts`) считаются запросом по `search_results`, не хранятся — так исключение
«с пересчётом» бесплатно и всегда честно.

## 5. Правила, которые проверяют эксперты (их нельзя нарушать)

**Достоверность (10 баллов — самый дорогой критерий).**
- Ссылка, текст, дата, название источника берутся **только из ответа площадки**. LLM не пишет ни
  заголовков, ни выдержек, ни ссылок.
- Выдержка — **дословный** фрагмент `publications.text` (ML даёт только позиции `excerpt_span`;
  search вырезает и проверяет, что это подстрока). Нет span — первые 300 символов.
- Заголовок: есть у площадки → он (`title_source=title`); нет → первые ~120 символов поста по границе
  слова (`title_source=post_start`, в UI помечено).
- Нет даты / метрики → `null` → в UI «нет данных». Никаких «сейчас» и нулей вместо неизвестного.
- Ссылки из поисковиков (Yandex Search по `site:ok.ru`) **не попадают в подборку как есть**: collector
  открывает каждую ссылку, достаёт текст и дату со страницы; не открылась — поста нет.
- Демо-фикстуры (`COLLECTOR_FAKE=true`) только для разработки. На демо — выключены, это проверяется
  в `GET /health/ready` и в README.

**Учёт публикаций.**
- Одна публикация = одно размещение: `(platform, source_external_id, post_external_id)`. Одна новость
  в трёх группах — три записи.
- Каноничная ссылка строится collector'ом из id, а не берётся «как пришла»:
  VK `https://vk.com/wall{owner_id}_{post_id}`, OK `https://ok.ru/group/{gid}/topic/{tid}`,
  MAX — по итогам spike B1-01.
- Повторное обнаружение того же поста (другая цель, другая фраза, retry) не создаёт записи и не
  увеличивает счётчик.
- Репост в другой группе — отдельное размещение этой группы (`is_repost=true`, ссылка на оригинал).

**Регион (объяснить пользователю в UI одной строкой).**
«Публикация относится к Красноярскому краю, если источник помечен как региональный **или** в тексте
есть привязка к краю (город, район, организация)». В карточке — два бейджа: «Региональный источник»,
«Упоминается: Ачинск». В режиме `global` пост без обоих признаков → `irrelevant` с объяснением
«нет привязки к Красноярскому краю». В режиме `selected` регион информационный (источники выбрал человек).

**Состояния.** «Подходящие публикации не найдены» (`completed`, `total=0`, видно, где искали) ≠ ошибка
(`failed` / цели `failed` с текстом и «Повторить»). Частичный результат сохраняется и показывается.

**Разделение поисков.** У каждой подборки свой `search_id` в URL и плашка параметров над списком.
Поменял поле после поиска — плашка «Параметры изменены, показана подборка по прежним условиям» и
кнопка «Найти заново». Старые результаты в новый поиск не подмешиваются.

## 6. Ошибки

Формат и маппинг — как в шаблоне (README §10). Новые коды:

| code | где | HTTP |
|---|---|---|
| `UNSUPPORTED_URL` | collector/search | 422 |
| `SOURCE_NOT_FOUND` | collector/search | 404 |
| `SOURCE_PRIVATE` | collector | 409 |
| `SOURCE_ALREADY_EXISTS` | search | 409 |
| `PLATFORM_UNAVAILABLE` | collector | 503 |
| `RATE_LIMITED` | collector | 429 |
| `SEARCH_NOT_FOUND` / `RESULT_NOT_FOUND` | search | 404 |
| `SEARCH_INVALID_PARAMS` | search | 422 |
| `SEARCH_NOT_FINISHED` | search | 409 |
| `ML_UNAVAILABLE` | ml | 503 |

Ошибки **целей** внутри поиска — не HTTP-ошибки, а `targets[].error {code, message}` (message — по-русски,
для пользователя).

## 7. Внешние сервисы и доступы (обновлять по мере получения)

| Что | Зачем | Кто получает | Статус |
|---|---|---|---|
| VK сервисный ключ (приложение VK ID) | `wall.get`, `groups.getById` | B1 | ✔ работает; `newsfeed.search` закрыт ключу (1051) |
| OK — публичные страницы групп | посты групп | B1 | ✔ без ключа |
| MAX — токен бота (Bot API) | посты каналов | B1 | ✘ выдают только юрлицу / ИП |
| Ollama на ноутбуке команды (GPU) | отбор, объяснения | ML | ✔; для сервера — обратный SSH-туннель |
| Yandex Cloud: YandexGPT + эмбеддинги | запасной отбор | ML | — не подключали (код готов) |
| Yandex Cloud: Search API | поиск по всей площадке VK / OK | B1 | — не подключали (платный, код готов) |
| Каталог источников края | seed `sources` | TL | ✔ `seed/sources.xlsx` |
| Сервер для демо | деплой | TL | ✔ `109.196.167.204:8080` |

Секреты — только в `.env` (в git — `.env.example` с пустыми значениями).

## 8. Вехи (48 часов)

| Время | Веха | Что должно работать |
|---|---|---|
| **H+2** | Контракты заморожены v1 | proto + openapi в main, `make proto`, сервисы созданы, у всех стабы; фронт на Prism |
| **H+6** | Скелет end-to-end | поиск проходит весь путь на стабах collector/ml; фронт показывает статус и список с реального gateway |
| **H+12** | **MVP-1 (сценарии 1, 4, 5 на VK)** | VK по выбранным источникам, ML v1 (эмбеддинги/эвристика), дедуп, XLSX, пусто ≠ ошибка |
| **H+24** | **MVP-2 (все 5 сценариев)** | + OK и MAX, режим global, ML v2 (LLM + «та же новость»), группы, retry, исключение |
| **H+34** | Фичи | тональность, вкладка «отсеяно», новостные сайты, расширение, DOCX, импорт XLSX, eval-метрики |
| **H+38** | **Feature freeze** | только баги, демо-данные, README, деплой |
| **H+44** | Прогон демо ×2 на сервере | 5 сценариев по чек-листу, запись видео-страховки |
| H+48 | Сдача | |

Правило: **ничего нового после H+38**. Сломалось на демо — лучше честная пометка «имитация», чем падение.

## 9. Владение файлами и git

- TL: `compose.yaml`, `infra/`, `.github/`, `contracts/**`, `services/gateway/**`, `Makefile`, `README.md`.
- B1: `services/collector_service/**`. B2: `services/search_service/**`. ML: `services/ml_service/**`, `eval/**`.
- FE: `frontend/**`, `extension/**`. UI (дизайнер): Figma, `docs/ui/**`, презентация.
- Контракт меняется только PR'ом от/через TL: правка `.proto`/`openapi.yaml` → `make proto` → сообщение в чат.
- Ветки `b1/…`, `b2/…`, `ml/…`, `fe/…`, PR в `main`, перед пушем `make fmt && make check`.
- Каждая задача закрыта = DoD выполнен + `make check` зелёный + отметка в `docs/tasks/<роль>.md`.

## 10. Что показываем как «работает / имитация / план» (README и презентация)

Таблица «функция · статус · как проверено» — [`STATUS.md`](STATUS.md), сводка — в README.
