# TL — тимлид / DevOps / gateway

Зона: `contracts/**`, `services/gateway/**`, `compose.yaml`, `infra/**`, `.github/**`, `Makefile`,
`README.md`, `docs/**`. Твоя главная работа — **чтобы все остальные не ждали**: контракты, стабы,
интеграция, доступы, демо.

## Старт после pull

```bash
git pull && make install                 # .env + uv sync во всех сервисах
make check                               # ruff + mypy --strict + pytest в 4 сервисах — как job «python» в CI
make proto && git diff --stat -- packages/platform_contracts docs/API.md docs/GRPC.md docs/api-types.ts
                                         # пусто = как job «contracts»
(cd frontend && npm install && npm run typecheck && npm run build)
```

Стенд — вариант Б из [README → «Быстрый старт после pull»](../../README.md#быстрый-старт-после-pull)
(4 терминала без Docker), затем:

```bash
curl http://127.0.0.1:8000/health/ready  # "status": "ok", search / collector / ml — "up"
make smoke URL=http://127.0.0.1:8000     # в конце «All good»
```

Что должно получиться: smoke зелёный на `COLLECTOR_FAKE=true`; Swagger http://127.0.0.1:8000/docs
показывает все 17 ручек. Вариант А (`make up`) — твоя первая задача ниже (TL-11), в сборке `main` он
не проверялся.

## Что изменилось при сборке `main`

- `main` = ветка `integ-main`: слиты `b1/layers-and-vk-connector`, `searcher` (B2), `feat/ml-02-eval-dataset`,
  `fe-01-base` и исправления интеграции. До этого `main` был красным: не было сгенерированного
  `platform_contracts`.
- search_service отдаёт gRPC по `contracts/search/v1/search_service.proto` на 50053 (решение владельца
  проекта): ветка B2 была переписана на FastAPI, её сценарии оставлены, поверх — хэндлеры медиатора.
  Gateway менять не пришлось.
- CI зелёный: 4 сервиса + `contracts` + `frontend` (сборка) + `compose config`.
- Сквозной прогон через gateway без Docker пройден руками и `make smoke` (список проверок — в
  [`docs/STATUS.md`](../STATUS.md)).

---

### [x] TL-01 · P0 · к H+1 · каркас сервисов
> Сделано: auth и example удалены; search / collector / ml созданы по шаблону, проведены в compose, CI,
> gateway, env, ansible; `make check` зелёный. **Не проверено:** `make up` → все контейнеры healthy —
> вынесено в TL-11.

### [ ] TL-02 · P0 · к H+2 · контракты v1 — заморозка
> Сделано: proto и `openapi.yaml` сверены между собой; сгенерированный код и справочники свежие (CI job
> `contracts` зелёный); Prism поднимали (`npm run mock`), FE-01…05 сверстаны по типам из `openapi.yaml`.
> Осталось: п. 3.

**Сделать.**
1. ~~Пройти контракты с командой~~ — сделано по ходу интеграции; новые расхождения не найдены.
2. ~~`make proto`, коммит сгенерированного кода~~ — сделано.
3. Объявить в чате «контракт v1 заморожен». Дальше правки только через тебя: правка → `make proto` →
   коммит `packages/` и `docs/` → сообщение в чат, что изменилось.

**DoD.** Сообщение о заморозке в чате; `make proto` после pull не даёт diff.

### [x] TL-03 · P0 · к H+6 · роутеры gateway
> Сделано: все 17 ручек, схемы 1:1 с openapi, enum'ы — `schemas/enums.py`, `UNIMPLEMENTED` → 501,
> `details` для `SEARCH_INVALID_PARAMS`, тесты на фейковых стабах (зелёные в CI). Проверено вживую через
> настоящий search_service: площадки, resolve, источники (409 на дубль, PATCH, DELETE), поиск selected и
> global, results, groups, exclusion, XLSX, retry, cancel, 422 с `details`, 404, `/health/ready`.
> Не проверено: импорт (search_service отвечает 501, B2-10).

Справка по маппингу (поля HTTP — [`docs/API.md`](../API.md), поля gRPC — [`docs/GRPC.md`](../GRPC.md)):

| HTTP (operationId) | gRPC | Маппинг, на что смотреть |
|---|---|---|
| `GET /platforms` (listPlatforms) | `collector.v1.CollectorService/GetPlatforms` | `PlatformInfo`: `code`←`platform`, `source_mode`←`source_mode_supported`, `global_mode`←`global_mode_supported`, `status`←`health`, `note` пусто → `null` |
| `POST /query/analyze` (analyzeQuery) | `ml.v1.MlService/AnalyzeQuery` | подмножество `QueryAnalysis`: `query_type, summary, search_queries, needs_clarification, clarification_hint` (пусто → `null`) |
| `GET /sources` (listSources) | `search.v1.SearchService/ListSources` | `platform[]`→`platforms`, `items`←`sources` |
| `POST /sources/resolve` | `SearchService/ResolveSource` | `SourcePreview` 1:1, `optional` → `null` |
| `POST /sources` (createSource) | `SearchService/CreateSource` | `is_regional` по умолчанию `true` (в proto bool, по умолчанию false — подставляет gateway) |
| `PATCH /sources/{id}` | `SearchService/UpdateSource` | в proto только присланные поля (`model_fields_set`) |
| `DELETE /sources/{id}` | `SearchService/DeleteSource` | 204 |
| `POST /sources/import` | `SearchService/ImportSources` | `UploadFile.read()` → `xlsx`; `failed[]`: `{row, value, code←error.code, message←error.message}` |
| `POST /searches` (startSearch) | `SearchService/StartSearch` | **202**; `mode`, `platforms` → enum |
| `GET /searches` (listSearches) | `SearchService/ListSearches` | `Search` → `SearchSummary` |
| `GET /searches/{id}` | `SearchService/GetSearch` | `Search` целиком |
| `POST /searches/{id}/retry` | `SearchService/RetrySearch` | **202**; тело необязательно |
| `POST /searches/{id}/cancel` | `SearchService/CancelSearch` | |
| `GET /searches/{id}/results` | `SearchService/ListResults` | query → `ResultFilter` + `ResultSort`; `items`←`results` |
| `GET /searches/{id}/groups` | `SearchService/ListGroups` | `items`←`groups`, `ResultGroup.items`←`results` |
| `POST /searches/{id}/results/exclusion` | `SearchService/SetExcluded` | `{counts}` |
| `GET /searches/{id}/export` | `SearchService/ExportSearch` | `Response(content, media_type=mime_type, Content-Disposition(filename))` |

Enum'ы: префикс убрать, нижний регистр; исключения `RELEVANCE_IRRELEVANT` ⇄ `"rejected"`,
`SENTIMENT_UNSPECIFIED` / `QUERY_TYPE_UNSPECIFIED` → `null`, `PLATFORM_HEALTH_*` → `ok|degraded|unavailable`.

### [ ] TL-11 · P0 · сразу после merge · стенд в Docker (`make up`)
**Цель.** Общий DoD («работает в `make up`») и деплой (TL-07) опираются на Docker, а в сборке `main` он
ни разу не поднимался. Риски: образ `search_service` новый (Dockerfile по шаблону: python 3.13, uv,
`alembic upgrade head && search-service`) и не собирался; `COLLECTOR_FAKE` приходит из `.env`.

**Сделать.**
1. `make reset && make up` (или `bash scripts/diagnose.sh --docker` — соберёт, проверит health, прогонит
   smoke и сложит логи в `.diagnose/`).
2. `make ps` — все running; `make logs s=search_service` — миграция применилась, сервер слушает 50053.
3. `curl localhost:8000/health/ready` — все `up`; `make smoke` → `All good`.
4. http://localhost — фронт из nginx открывается, поиск «Безопасность дорожного движения» в режиме
   «Только мои источники» доходит до подборки (после smoke в каталоге есть источник).
5. Что сломалось — починить (compose, Dockerfile) или отдать владельцу сервиса с логом.

**DoD.** На чистой машине `make install && make up && make smoke` → `All good`; строка в `docs/STATUS.md`
«стенд в Docker» переведена в ✔ с датой.

### [ ] TL-12 · P0 · сразу после merge · все на новом `main`
**Сделать.**
1. Сообщение в чат: «main собран из всех веток; каждый — `git pull` и раздел «Старт после pull» в своём
   файле `docs/tasks/<роль>.md`; новые ветки — только от свежего `main`».
2. Слитые ветки (`b1/layers-and-vk-connector`, `searcher`, `feat/ml-02-eval-dataset`, `fe-01-base`) закрыть,
   чтобы в них не продолжали работу. У FE есть незалитая ветка с FE-06 — ребейз на `main` (FE-06).
3. B2: отдельно объяснить, что сервис теперь gRPC, а не FastAPI (раздел «Что изменилось» в B2-search.md).

**DoD.** Каждый подтвердил в чате, что у него проходит «Старт после pull» своей роли.

### [ ] TL-04 · P0 · к H+4 · доступы — **блокирует реальные данные**
**Цель.** Без ключей весь продукт работает только на тестовых постах и эвристиках.

**Сделать.** VK ID приложение → сервисный ключ → B1 (`VK_SERVICE_TOKEN`; без него VK отвечает 503
«не настроен доступ»). Yandex Cloud: каталог, сервисный аккаунт, API-ключ, роли `ai.languageModels.user`
(ML: `YC_FOLDER_ID`, `YC_API_KEY`) и для Search API (B1: `YC_SEARCH_API_KEY`) — проверь грант/бюджет.
Сервер для демо. Стартовые материалы кейса (список источников, сайтов, «согласованные доступы») — как
придут, в `docs/ARCHITECTURE.md §7` и в `.env` на сервере.

**DoD.** Таблица §7 в ARCHITECTURE заполнена, у B1 и ML рабочий ключ в локальном `.env`.

### [ ] TL-05 · P0 · на H+12, H+24, H+34 · интеграционный прогон
> Сделано: чек-лист `docs/demo/checklist.md`; `scripts/smoke.py` (источник → поиск → финальный статус →
> results → groups → XLSX, строк со ссылками = `counts.total` → 404) проходит локально без Docker на
> тестовых данных.

**Сделать.** На каждой вехе: `make smoke` на стенде + 5 сценариев ТЗ руками по чек-листу, отметки в
таблице чек-листа. Баги — в чат с ID задачи владельца. Как только у B1 есть ключ VK — первый прогон с
`COLLECTOR_FAKE=false` (smoke сам возьмёт `vk.com/krsk_news`).

**DoD.** Чек-лист с отметками по каждой вехе; `make smoke` проходит на Docker-стенде и на сервере.

### [ ] TL-06 · P0 · к H+14 · каталог источников (seed)
> 2026-10-19: `scripts/seed_sources.py`, `make seed [URL=...]` и шаблон `seed/sources.xlsx` (только шапка) готовы; скрипт проверен на заглушке сервера.
> Осталось: сам список 30–50 источников (стартовые материалы кейса) и прогон с ключом VK.
> 2026-10-19 (вечер): `seed/sources.xlsx` заполнен — 53 источника (50 VK, 3 OK): власть, ГИБДД/МЧС/МВД, СМИ и ТВ, городские паблики, Норильск/Ачинск/Канск/Минусинск/Железногорск. Все открылись через VK API (токен VK ID) и дали ≥ 2 постов за 7 дней (прогон «выбранные», 12–19.10); пустые и почти пустые убраны. Колонки D–E — категория и число постов за неделю (скрипт их не читает).
**Цель.** Режим «везде» и демо работают на реальных региональных источниках.

**Сейчас:** нет ни `seed/`, ни скрипта, ни цели `make seed` (на неё ссылаются TL-08 и DoD ниже).

**Сделать.**
1. Из стартовых материалов (или вручную: 30–50 источников — крупные СМИ края, правительство,
   ГИБДД/МЧС края, мэрии крупных городов в VK, OK, MAX) → `seed/sources.xlsx` (A — ссылка, B — название,
   C — региональный).
2. `scripts/seed_sources.py URL` — по строкам `POST /api/v1/sources` (409 = уже есть, не ошибка), в конце
   отчёт «добавлено / уже были / ошибки со строкой». Цель `make seed [URL=...]`. Импорт через
   `POST /sources/import` (B2-10, P2) — не ждать.
3. Учесть: имена берутся с площадки, поэтому seed осмыслен только с ключом VK (TL-04, B1-03); на
   `COLLECTOR_FAKE=true` получатся тестовые имена. Строки OK и MAX до B1-04/B1-05 дадут 501 — оставить
   в файле, скрипт их просто отчитает как ошибки.

**DoD.** После `make reset && make up && make seed` в каталоге ≥ 30 источников VK, у всех `name` с площадки.

### [ ] TL-07 · P0 · к H+30 · деплой
**Сделать.** После TL-11: `make deploy HOST=…` (`infra/ansible`, ещё не запускали); `.env` на сервере с
ключами; `COLLECTOR_FAKE=false`, проверка в `/health/ready` и `/platforms`; фронт и расширение смотрят на
адрес сервера. Ежедневный (ежечасный перед демо) `make smoke URL=http://<ip>`.

**DoD.** Эксперт открывает `http://<ip>` и проходит сценарий 1 без нас.

### [ ] TL-08 · P0 · к H+38 · README по требованиям ТЗ
> 2026-10-19: добавлены разделы «Что это и как пользоваться», «Как запустить», «Поддерживаемые площадки», «Как отбираем и считаем»,
> «Модели и внешние сервисы», «Доступы для экспертов», «Демо-запросы», «Работает / имитация / план», «Известные ограничения».
> Осталось: скриншоты (после FE-12), раздел B1-10 и данные ML-09, адрес стенда, проверка «чужим человеком».
> Сделано: «Быстрый старт после pull» (зависимости, Docker / без Docker, Windows, фронт, проверки, smoke,
> какие ключи что включают). Остальные разделы — нет.

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
> 2026-10-19: сценарий показа, проверки «перед показом» и распределение вопросов — [`docs/demo/script.md`](../demo/script.md).
> Осталось: регламент по времени, слайд «Качество» (цифры ML-09), два прогона на сервере, видео-страховка.
**Сделать.** Сценарий показа на одном сквозном примере (критерий «Демонстрация» 5 баллов): запрос →
период → источники → поиск (видно прогресс и охват) → спорные → открыть 2–3 ссылки → исключить →
XLSX → открыть файл. Отдельно: сценарий 2 (текст новости), сценарий 5 (отключённый источник).
Слайд «Качество» — таблица precision/recall/время из ML-09. Два прогона на сервере; видео-страховка.
Разделить вопросы: кто отвечает про сбор (B1), отбор (ML), архитектуру (TL), UX (FE).

**DoD.** Прогон укладывается в регламент, каждый знает свою часть.

### [ ] TL-10 · P1 · по ходу · ревью и «проверенное vs предположения»
Ревьюить PR в `main` (приоритет: контрактные и B2). Вести `docs/STATUS.md` — что реально проверено,
что предположение (критерий «Выступление и ответы»). Последнее обновление — после сборки `main`.

### [ ] TL-13 · P1 · по ходу · мелочи CI и Makefile, найденные при сборке
> 2026-10-19: п. 1 (`npm run typecheck` в job `frontend`), п. 3 (`make env` создаёт `services/*/.env`), п. 4 (`outputs/` удалена по согласованию),
> п. 5 (`make seed`) сделаны. Осталось: убедиться, что CI зелёный.
1. Job `frontend` делает только `npm run build` (это `vite build`, типы не проверяет) — добавить
   `npm run typecheck`.
2. ~~`make front-dev` проксировал в Prism вопреки подписи~~ — исправлено при сборке main: теперь
   передаёт `VITE_API_TARGET=http://127.0.0.1:8000`.
3. `make install` не создаёт `services/<сервис>/.env`, а без него `make run s=collector_service`
   стартует с `COLLECTOR_FAKE=false` (по умолчанию в коде). Решить: копировать `.env.example` в `make env`
   или оставить шаг в README.
4. В корне лежит папка `outputs/` — старая копия `docs/` из первого коммита; её никто не обновляет.
   Удалить после согласования с владельцем проекта.
5. Цель `make seed` — в TL-06.

---

## Кто от кого ждёт (интеграция)

| Что | Кто ждёт | От кого | Чем закрывается |
|---|---|---|---|
| Реальные посты VK | все сценарии, демо, eval ML | TL-04 (ключ) → B1-03 | `COLLECTOR_FAKE=false` + `VK_SERVICE_TOKEN`, smoke на `krsk_news` |
| Каталог источников | режим «везде», демо | B1-03 → TL-06 | `make seed` |
| OK / MAX | 5 баллов «Площадки» | B1-01 → B1-04 / B1-05 / B1-06 | сейчас 501 |
| Отбор по смыслу | сценарии 1–2, «Качество» | TL-04 (ключи Яндекса) → ML-03…ML-06 → B2-06 (боевой прогон) | сейчас эвристики, `degraded=true` |
| Фронт на живых данных | демо | FE-12 (прогон на gateway) | сейчас FE проверен на MSW |
| Docker и сервер | деплой, эксперты | TL-11 → TL-07 | сейчас только локальный стенд без Docker |
