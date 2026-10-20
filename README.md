# MP — медиамониторинг соцсетей

Кейс финала Первенства России по продуктовому программированию: сотрудник агентства одним полем
задаёт тему / событие / человека / текст новости, выбирает период и источники, получает подборку
**реальных** публикаций VK / OK / MAX с прямыми ссылками и выгружает XLSX.

- Архитектура и правила продукта — [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Задачи по ролям — [`docs/tasks/`](docs/tasks/README.md) (в начале каждого файла — «Старт после pull»)
- Что работает, что имитация, что в плане — [`docs/STATUS.md`](docs/STATUS.md)
- HTTP API для фронта — [`docs/API.md`](docs/API.md) (источник: `contracts/http/openapi.yaml`)
- gRPC между сервисами — [`docs/GRPC.md`](docs/GRPC.md) (источник: `contracts/*/v1/*.proto`)

```
Браузер / расширение ──HTTP──▶ frontend (nginx :80) ──▶ gateway (FastAPI :8000)
                                                          │ gRPC
              ┌───────────────────────────────────────────┼──────────────────────┐
              ▼                                           ▼                      ▼
   search_service :50053 ──gRPC──▶ collector_service :50054        ml_service :50055
   источники, поиски, подборка,    VK / OK / MAX / сайты            разбор запроса, отбор,
   дедуп, экспорт  ──▶ search_db   (без БД)                          группы (без БД)
              └──────────────────────gRPC──────────────────────────────▲
```

| Сервис | Владелец | Порт | Что внутри |
|---|---|---|---|
| `gateway` | TL | 8000 | HTTP-схемы по `openapi.yaml`, маппинг ошибок; `/platforms` → collector, `/query/analyze` → ml, остальное → search |
| `search_service` | B2 | 50053, БД 5435 | gRPC `search.v1` поверх сценариев B2 (Mediator → хэндлеры), UoW, Postgres, клиенты collector и ml |
| `collector_service` | B1 | 50054 | коннекторы площадок + общие гарантии (период, дубли, лимиты); `COLLECTOR_FAKE=true` — тестовые посты |
| `ml_service` | ML | 50055 | `core/` (чистая логика) + провайдеры LLM/эмбеддингов (пока только `stub`) |
| `frontend` | FE | 80 / 5173 | React 19 + Vite 7 + Mantine 9 + react-query + openapi-fetch; моки — MSW или Prism |

Авторизации нет — по ТЗ регистрация не нужна.

## Что это и как пользоваться

Инструмент для сотрудника агентства, который отвечает на вопрос «где и что о нас написали». Один раз
собираешь список источников (группы и каналы), потом задаёшь тему и период — и получаешь подборку
публикаций с прямыми ссылками, которую можно проверить и выгрузить в Excel.

1. **Источники.** Вставь ссылку на группу — система покажет название и площадку («Уже в списке», если
   такая есть) и добавит в каталог. Список можно загрузить файлом XLSX (колонки: ссылка, название,
   региональный да/нет).
2. **Запрос.** Одно поле для темы, события, человека или полного текста новости. Расплывчатый запрос
   («новости») система предложит уточнить.
3. **Период и режим.** Даты (по времени Красноярска) и режим: «Только мои источники» или «Везде»
   (все площадки целиком + источники каталога, с отбором по Красноярскому краю).
4. **Подборка.** Пока идёт поиск, видны стадия, прогресс и блок «Где искали» (по каждому источнику:
   сколько получено, сколько попало в подборку, что не удалось). В карточке: заголовок, дословная
   выдержка, дата, ссылка на публикацию, «почему попало» — прямая / косвенная / спорная связь.
   Не нашлось ничего — это «публикации не найдены», а не ошибка; упавшие источники можно «Повторить».
5. **Проверка и выгрузка.** Лишнее исключаешь вручную (счётчики пересчитываются), копии одной новости
   сгруппированы в сюжеты, но каждое размещение считается отдельно. Выгрузка XLSX (и DOCX) содержит
   ровно то, что на экране.

_Скриншоты шагов — добавить после прогона фронта на живом gateway (FE-12): сейчас экраны проверены
только на моках, не на реальных данных._

## Как запустить

- **Веб (стенд).** Адрес появится после деплоя (TL-07, `make deploy`); эксперту достаточно открыть
  `http://<адрес стенда>`. Сейчас стенда на сервере нет.
- **Локально:** `make install && make up && make seed` — фронт на http://localhost, Swagger на
  http://localhost:8000/docs. `make up` (Docker) в сборке `main` ещё **не проверяли** — рабочий путь без
  Docker описан в разделе «Быстрый старт после pull» ниже (вариант Б). `make seed` наполняет каталог из
  `seed/sources.xlsx` (файл заполняется списком источников края; с `COLLECTOR_FAKE=true` имена будут
  тестовыми).
- **Расширение Chrome.** Каталога `extension/` пока нет (FE-10). План: `chrome://extensions` → «Режим
  разработчика» → «Загрузить распакованное» → папка `extension/`, права администратора не нужны.

## Поддерживаемые площадки

Подробно (методы, лимиты, ограничения, как проверено, тексты ошибок) —
[«Как получаем публикации»](services/collector_service/README.md#как-получаем-публикации-b1-10).

| Площадка | Как получаем | Режимы | Что нужно |
|---|---|---|---|
| ВКонтакте | официальный VK API (`wall.get`, `groups.getById`); «везде» — через Яндекс `site:vk.com`, потому что `newsfeed.search` закрыт нашему типу ключа (ошибка 1051) | мои источники, везде | ключ VK |
| Одноклассники | публичные страницы групп без входа (в API OK нет метода «посты группы»); «везде» — через Яндекс `site:ok.ru` | мои источники, везде | — |
| MAX | Bot API: сообщения каналов, где наш бот — администратор | только мои источники (поиска у Bot API нет) | токен бота |
| Новостные сайты | RSS-ленты сайтов из перечня (`NEWS_SITES`), анонс → открываем статью | мои источники, везде (по свежим лентам) | — |

Ограничения сбора: на источник — до 150 постов, на поиск «везде» — до 200 (в Docker), 50 секунд на
сбор: не успели — отдаём собранное с пометкой «частично». Ссылка, текст и дата — только из ответа
площадки: не открылся пост — в подборку не идёт.

## Как отбираем и считаем

- **По смыслу, а не по словам.** Запрос разбирает ML (`AnalyzeQuery`): тип запроса, поисковые фразы,
  сущности. Каждый пост получает оценку связи: прямая / косвенная / спорная / не связана, объяснение
  и положение выдержки. Работают **локальные модели** (Ollama): эмбеддинги `bge-m3` отсекают явно
  далёкое, LLM `qwen2.5:7b-instruct` судит остальное и пишет объяснение одним предложением по тексту
  поста. Без моделей — эвристики (`degraded=true`, предупреждение «ML работал в упрощённом режиме»).
  Подробно — [`services/ml_service/README.md`](services/ml_service/README.md).
- **Та же новость.** Для вставленного текста новости копия, сокращение и пересказ — прямые; похожая
  новость о другом событии отсеивается с объяснением («другое место (Норильск), другие цифры»).
- **Регион.** Пост относится к Красноярскому краю, если источник помечен региональным **или** в тексте
  есть привязка к краю. В режиме «Везде» пост без обоих признаков отсеивается с объяснением;
  в режиме «Только мои источники» регион информационный.
- **Достоверность.** Ссылка, текст, дата и название источника берутся только из ответа площадки;
  выдержка — дословный фрагмент текста поста (нет позиции от ML — первые 300 символов); заголовок —
  заголовок площадки либо начало поста (помечено); неизвестная дата не выдаётся за «в периоде».
- **Без двойного учёта.** Пост определяется тройкой «площадка + источник + id поста»; найденный
  дважды (другая фраза, другой источник, повтор поиска) — одна запись. Один текст в трёх группах —
  три размещения, потому что это три публикации.
- **Группы.** Копии, сокращения и пересказы одной новости собираются в сюжет для удобства просмотра;
  в счётчике каждое размещение отдельно, внутри сюжета видны все ссылки.

## Модели и внешние сервисы

| Что | Зачем | Состояние |
|---|---|---|
| Ollama: `qwen2.5:7b-instruct` + `bge-m3` (`LLM_PROVIDER=ollama`, `EMBED_PROVIDER=ollama`) | отбор по смыслу, объяснения, тональность, группы | написано и покрыто тестами; на настоящих моделях — `bash scripts/ml_check.sh` |
| Эвристики `ml_service` (`LLM_PROVIDER=stub` или модель недоступна) | разбор запроса, оценка, группы без моделей | работает, это упрощённый режим |
| Yandex Search API (`YC_SEARCH_API_KEY`) | глобальный поиск по OK / MAX / сайтам | не подключён |

Модели локальные: текст запроса и тексты публичных постов уходят только в Ollama на той же машине,
наружу ML ничего не отправляет; денег не стоит, цена — время (`eval/report.md`) и память GPU.

## Доступы для экспертов

Стенд на сервере с настроенными ключами готовится (TL-04, TL-07): эксперту не придётся покупать
подписки или заводить аккаунты — всё будет уже настроено на стенде. До этого проект запускается
локально на тестовых данных.

## Демо-запросы и примеры выгрузок

Сценарий показа — [`docs/demo/script.md`](docs/demo/script.md), чек-лист прогонов —
[`docs/demo/checklist.md`](docs/demo/checklist.md). XLSX с реальных прогонов появятся в `docs/demo/`
после получения ключа VK (сейчас данные тестовые и помечены `[FAKE]`).

## Работает / имитация / план

Полная таблица с тем, как проверяли каждую строку, — [`docs/STATUS.md`](docs/STATUS.md).

| | Состояние |
|---|---|
| Работает (проверено запуском, на тестовых данных) | gateway и 17 ручек; каталог источников; поиск «по источникам» и «везде»; пайплайн со статусами и частичным результатом; повтор и отмена; исключение вручную; XLSX; `make smoke` |
| Написано, проверено только тестами на фейках | регион в «везде», `matched` после оценки, DOCX, импорт источников из XLSX, `request_id` до соседей, `make seed` |
| Имитация | данные площадок (`COLLECTOR_FAKE=true`), отбор (эвристики вместо моделей) |
| Ждёт доступа | реальные посты VK (ключ), модели Яндекса (ключи) |
| В плане / не сделано | OK и MAX, новостные сайты, расширение Chrome, фронт на живом gateway, Docker-стенд и деплой, каталог источников края |

## Известные ограничения

- Реальных публикаций мы пока не получали ни с одной площадки; все примеры — тестовые.
- Точность отбора измерена только на придуманных постах (`eval/report.md`); на эвристиках «Тема»
  находит мало (recall 24 % на БДД) — смысл ловят модели, без них поиск работает, но слабее.
- Одновременно собирается не более 5 источников; GroupPosts режется по 500 постов — копии, попавшие
  в разные куски, в один сюжет не склеятся.
- Импорт источников идёт по очереди (строка за строкой) и до 500 строк за раз.
- `make up` (Docker), деплой и расширение не проверены / не сделаны.

## Быстрый старт после pull

`main` собран из всех веток команды (сборщик B1, поиск B2, eval-наборы ML, фронт FE-01…05) плюс
исправления интеграции. CI зелёный по всем четырём сервисам, контрактам и сборке фронта. Сквозной
сценарий (площадки → источник → поиск → подборка → группы → исключение → XLSX → повтор → отмена)
**проходит через gateway локально без Docker** на тестовых данных (`COLLECTOR_FAKE=true`).
Через Docker (`make up`) стенд в этой сборке **не проверяли** — в среде, где собирали `main`, нет
Docker-демона (задача TL-11).

### 0. Что поставить

| Что | Зачем | Обязательно |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) + Python 3.13 (`uv python install 3.13`) | все Python-сервисы | да |
| Node 22 + npm | фронт | для фронта |
| Postgres 16/17 на `127.0.0.1:5435` **или** Docker | БД `search_service` | для стенда |
| Docker + compose + buildx | `make up` / `make db` | нет (можно без Docker) |
| `make` + bash | команды `make …` | нет: на Windows — WSL или Git Bash с make; без make — команды ниже напрямую |
| Ansible + rsync | только деплой | нет |

**Windows.** Запись `ПЕРЕМЕННАЯ=значение команда` и `sh -c '…'` — синтаксис bash (Git Bash / WSL).
В PowerShell переменные ставятся отдельной командой `$env:ПЕРЕМЕННАЯ="значение"` (живут до закрытия
окна) — эквиваленты ниже. Везде пиши `127.0.0.1`, а не `localhost`: на Windows `localhost` уходит
в IPv6 `::1`, а сервисы и Prism слушают IPv4.

### 1. Зависимости

```bash
git pull
make install                       # .env и services/*/.env из .env.example + uv sync в каждом сервисе
cd frontend && npm install && cd ..
```

Без make (PowerShell):

```powershell
Copy-Item .env.example .env        # если .env ещё нет
foreach ($s in "gateway","search_service","collector_service","ml_service") { Push-Location services/$s; uv sync; Pop-Location }
cd frontend; npm install; cd ..
```

`make proto` после pull **не нужен**: сгенерированный код (`packages/platform_contracts`) и справочники
`docs/` лежат в git, CI проверяет, что они свежие. Запускать `make proto` — только после правки контракта.

### 2. Проверки — как в CI

```bash
make check                         # ruff + ruff format --check + mypy --strict + pytest во всех 4 сервисах
make proto && git diff --stat -- packages/platform_contracts docs/API.md docs/GRPC.md docs/api-types.ts
                                   # пусто = контракты и справочники свежие (job «contracts»)
cd frontend && npm run typecheck && npm run build   # job «frontend»
```

Один сервис: `cd services/<сервис> && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`.

### 3. Поднять стенд

#### Вариант А — Docker (не проверено в этой сборке)

```bash
make up          # фронт http://localhost, Swagger http://localhost:8000/docs
make ps          # все контейнеры running
make smoke       # сквозной сценарий через gateway → в конце «All good»
```

`.env` из `make install` содержит `COLLECTOR_FAKE=true` — данные тестовые. Если `make up` не
собирается или сервис не стартует — `make logs s=<сервис>` и сразу в чат TL (задача TL-11).

#### Вариант Б — без Docker (проверено)

База: любой локальный Postgres 16/17 на порту 5435 (или `make db` — только `search_db` в Docker,
пользователь и база создаются сами). Для своего Postgres один раз:

```bash
psql -h 127.0.0.1 -p 5435 -U postgres -c "CREATE ROLE search LOGIN PASSWORD 'search_local'" -c "CREATE DATABASE search OWNER search"
```

Если твой Postgres на 5432 — поменяй порт в `DATABASE_URL` ниже.

Четыре терминала из корня репозитория (bash):

```bash
# 1 — сборщик (тестовые посты)
cd services/collector_service && GRPC_ADDRESS=127.0.0.1:50054 COLLECTOR_FAKE=true uv run collector-service
# 2 — ML (эвристики)
cd services/ml_service && GRPC_ADDRESS=127.0.0.1:50055 LLM_PROVIDER=stub EMBED_PROVIDER=stub uv run ml-service
# 3 — поиск: миграции, потом сервер
cd services/search_service && DATABASE_URL=postgresql+asyncpg://search:search_local@127.0.0.1:5435/search GRPC_ADDRESS=127.0.0.1:50053 COLLECTOR_GRPC_TARGET=127.0.0.1:50054 ML_GRPC_TARGET=127.0.0.1:50055 sh -c 'uv run alembic upgrade head && uv run search-service'
#     офлайн, без соседей (терминалы 1–2 не нужны): добавь COLLECTOR_MODE=stub ML_MODE=stub
# 4 — gateway → http://127.0.0.1:8000/docs
cd services/gateway && SEARCH_GRPC_TARGET=127.0.0.1:50053 COLLECTOR_GRPC_TARGET=127.0.0.1:50054 ML_GRPC_TARGET=127.0.0.1:50055 uv run uvicorn gateway.main:app --host 127.0.0.1 --port 8000
```

То же в PowerShell (каждый блок — в своём окне, из корня репозитория):

```powershell
# 1 — сборщик
cd services/collector_service; $env:GRPC_ADDRESS="127.0.0.1:50054"; $env:COLLECTOR_FAKE="true"; uv run collector-service
# 2 — ML
cd services/ml_service; $env:GRPC_ADDRESS="127.0.0.1:50055"; $env:LLM_PROVIDER="stub"; $env:EMBED_PROVIDER="stub"; uv run ml-service
# 3 — поиск
cd services/search_service
$env:DATABASE_URL="postgresql+asyncpg://search:search_local@127.0.0.1:5435/search"; $env:GRPC_ADDRESS="127.0.0.1:50053"
$env:COLLECTOR_GRPC_TARGET="127.0.0.1:50054"; $env:ML_GRPC_TARGET="127.0.0.1:50055"
uv run alembic upgrade head
uv run search-service
# 4 — gateway
cd services/gateway; $env:SEARCH_GRPC_TARGET="127.0.0.1:50053"; $env:COLLECTOR_GRPC_TARGET="127.0.0.1:50054"; $env:ML_GRPC_TARGET="127.0.0.1:50055"
uv run uvicorn gateway.main:app --host 127.0.0.1 --port 8000
```

Через `make run` (Linux / macOS / WSL) — те же программы, только настройки берутся из
`services/<сервис>/.env` (каждый сервис читает `.env` в своей папке; `make install` / `make env`
создают их из `.env.example`, существующие не трогают; в collector там `COLLECTOR_FAKE=true`).
Этот путь в сборке `main` отдельно не прогоняли — проверяли переменные окружения выше:

```bash
make db                          # или свой Postgres на 5435
make run s=collector_service     # терминал 1
make run s=ml_service            # терминал 2
make run s=search_service        # терминал 3 (alembic upgrade head + сервер)
make run s=gateway               # терминал 4 → http://127.0.0.1:8000/docs (с --reload)
```

Проверка: `curl http://127.0.0.1:8000/health/ready` → `"status": "ok"`, все сервисы `up`.

### 4. Фронт

| Режим | Команда (из `frontend/`) | Откуда данные |
|---|---|---|
| MSW — без бэкенда, «живые» сценарии | `npm run dev:mocks` | моки в браузере: в запросе «безопасность» → частичный итог, группы, OK падает; «пусто» → ничего не найдено; «ошибка» → поиск не выполнен; текст > 300 символов → поиск по тексту новости; иначе — 10 результатов |
| Prism — статичные примеры из `openapi.yaml` | `npm run mock` (или `make mock` из корня) + во втором окне `npm run dev` | один пример на ручку |
| Живой gateway (стенд из шага 3) | `VITE_API_TARGET=http://127.0.0.1:8000 npm run dev` | настоящие сервисы |

PowerShell: `$env:VITE_API_TARGET="http://127.0.0.1:8000"; npm run dev`. Открывать
http://127.0.0.1:5173. `make front-dev` запускает фронт сразу против gateway (127.0.0.1:8000);
голый `npm run dev` без `VITE_API_TARGET` проксирует в Prism (127.0.0.1:4010).

### 5. Smoke

```bash
make smoke URL=http://127.0.0.1:8000        # = uv run --project services/gateway python scripts/smoke.py http://127.0.0.1:8000
```

Проходит путь пользователя (площадки → разбор запроса → источник → поиск → подборка → группы →
XLSX, где строк со ссылками = `counts.total` → 404) и печатает `All good`. Строка `collector: ТЕСТОВЫЕ
данные` — значит включён `COLLECTOR_FAKE=true`.

### 6. Режимы и ключи: что сейчас настоящее

| Переменная | Сервис | Значения | Сейчас |
|---|---|---|---|
| `COLLECTOR_FAKE` | collector | `true` — тестовые посты `[FAKE]`; `false` — площадки | при `false`: VK без ключа → 503 `PLATFORM_UNAVAILABLE` «ВКонтакте: не настроен доступ (VK_SERVICE_TOKEN)»; OK, MAX, сайты → 501 `NOT_IMPLEMENTED` (B1-04…B1-08); поиск «везде» завершается `failed` с причиной по каждой цели |
| `VK_SERVICE_TOKEN` | collector | сервисный ключ VK ID | ключа у команды пока нет (TL-04); с настоящим VK код не запускали |
| `YC_FOLDER_ID`, `YC_SEARCH_API_KEY` | collector | Yandex Search API — поиск «везде» по OK / MAX (B1-06) | не подключено |
| `LLM_PROVIDER`, `EMBED_PROVIDER` | ml | `stub` — эвристики, `degraded=true`; `ollama` — локальные модели | `ollama` написан; нет Ollama / модели — сервис стартует на эвристиках, причина в логе; `yandex` не реализован (тоже эвристики) |
| `YC_FOLDER_ID`, `YC_API_KEY` | ml | YandexGPT и эмбеддинги Яндекса | понадобятся после ML-03 |
| `COLLECTOR_MODE`, `ML_MODE` | search | `grpc` (по умолчанию) — настоящие соседи; `stub` — офлайн-заглушки | `stub` добавляет поиску предупреждение «имитация» |

Локальные модели: `ollama serve` на хосте (или `docker compose --profile llm-local up -d ollama`),
`ollama pull qwen2.5:7b-instruct && ollama pull bge-m3`, затем `LLM_PROVIDER=ollama EMBED_PROVIDER=ollama`
для ml_service. Проверка всего разом: `bash scripts/ml_check.sh --stack` (логи в `.ml_check/`). На сервере `COLLECTOR_FAKE=false` всегда.

## Как добавить / поменять RPC (контракт — точка синхронизации)

1. Правка `.proto` (и `openapi.yaml`, если меняется HTTP) — через TL.
2. `make proto` → коммит `packages/platform_contracts` и `docs/` (CI проверяет, что всё свежее).
3. Сервис: команда/запрос → хэндлер → регистрация в `dependencies.py` → метод servicer'а → маппер.
4. Ошибка = строка в `ERROR_CODES` (`transport/grpc/errors.py`); gateway отдаёт её код фронту.
5. Gateway: схема в `schemas/`, ручка в `routers/`.
6. `make fmt && make check`.

Пока сценарий не написан, хэндлер бросает `NotImplementedYetError` → gRPC `UNIMPLEMENTED` →
HTTP **501 `NOT_IMPLEMENTED`** с номером задачи в сообщении. Сейчас так отвечают: коннекторы
OK / MAX / сайты (B1-04…B1-08).

## Команды

| Команда | Что делает |
|---|---|
| `make install` / `make lock` | `.env` (корень и `services/*`) + `uv sync` / `uv lock` в каждом сервисе |
| `make proto` | Python из `contracts/**/*.proto` + `make docs` |
| `make docs` | `docs/API.md`, `docs/api-types.ts`, `docs/GRPC.md` из контрактов |
| `make mock` | Prism-мок HTTP API на :4010 |
| `make up` / `down` / `reset` / `ps` / `logs [s=...]` | Docker |
| `make db` / `make run s=<сервис>` | локальная разработка (Postgres в Docker / сервис из своей папки) |
| `make front-dev` | фронт на :5173, прокси `/api` → gateway 127.0.0.1:8000 |
| `make migration s=search_service m="msg"` | миграция alembic (autogenerate) |
| `make fmt` / `lint` / `typecheck` / `test` / `check` | ruff, mypy --strict, pytest (как в CI) |
| `make smoke [URL=...]` | сквозной тест живого стенда |
| `make seed [URL=...]` | каталог источников из `seed/sources.xlsx` через `POST /api/v1/sources` |
| `make deploy HOST=... SSH_USER=...` | деплой (ключи API — из окружения, см. `infra/ansible/README.md`) |
| `bash scripts/diagnose.sh [--mock] [--docker]` | диагностика окружения одним запуском, логи в `.diagnose/` |

## Порты и переменные

| Что | Порт | Наружу на сервере |
|---|---|---|
| frontend (nginx) | 80 | да — единственный |
| gateway / Swagger | 8000 | через nginx: `/api`, `/docs` |
| search / collector / ml | 50053 / 50054 / 50055 | нет (127.0.0.1) |
| search_db | 5435 | нет |
| vite dev / Prism | 5173 / 4010 | только локально |

Переменные compose — `.env.example`; у каждого сервиса свой `services/<сервис>/.env.example`
для локального запуска (таблица переменных search_service — в `services/search_service/README.md`).

## Отладка

- `request_id` — в заголовке `X-Request-ID` и в `error.request_id`; gateway и сервисы пишут его в лог
  (search_service передаёт его collector и ml, в том числе из фонового пайплайна).
- `curl http://127.0.0.1:8000/health/ready` — кто жив.
- gRPC напрямую (reflection включён): `grpcurl -plaintext 127.0.0.1:50054 list`,
  `grpcurl -plaintext -d '{"url":"vk.com/krsk_news"}' 127.0.0.1:50054 collector.v1.CollectorService/ResolveSource`.
- БД: `docker compose exec search_db psql -U search -d search` (Docker) или
  `psql -h 127.0.0.1 -p 5435 -U search -d search` (свой Postgres).

| Симптом | Что делать |
|---|---|
| `501 NOT_IMPLEMENTED` | сценарий ещё не написан — номер задачи в `error.message` |
| `503 SERVICE_UNAVAILABLE` | сервис не запущен: `make ps`, `make logs s=<сервис>` или его терминал |
| `503 PLATFORM_UNAVAILABLE` «не настроен доступ» | `COLLECTOR_FAKE=false` без `VK_SERVICE_TOKEN` |
| `502 UPSTREAM_ERROR` | исключение не из `ERROR_CODES` — traceback в логах сервиса |
| ручка не видит новый RPC | забыл `make proto` (в Docker — ещё `make up`) |
| фронт на Windows не видит API | `127.0.0.1` вместо `localhost` в `VITE_API_TARGET` |
| `ml_service` падает на старте | `LLM_PROVIDER` / `EMBED_PROVIDER` не `stub` — провайдеры ещё не написаны (ML-03 / ML-04) |
| Docker Hub не качается | `"registry-mirrors": ["https://mirror.gcr.io"]` в `/etc/docker/daemon.json` |
