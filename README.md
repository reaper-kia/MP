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
make install                       # .env из .env.example + uv sync в каждом сервисе
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
cd frontend && npm run typecheck && npm run build   # job «frontend» (в CI пока только build)
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
`services/<сервис>/.env` (каждый сервис читает `.env` в своей папке; `make install` их **не** создаёт).
Этот путь в сборке `main` отдельно не прогоняли — проверяли переменные окружения выше:

```bash
for s in services/*; do cp -n $s/.env.example $s/.env; done   # в collector .env уже COLLECTOR_FAKE=true
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
http://127.0.0.1:5173. `make front-dev` = `npm run dev`, то есть **по умолчанию проксирует в Prism
(127.0.0.1:4010)**, а не в gateway (подпись в `make help` устарела); на gateway —
`VITE_API_TARGET=http://127.0.0.1:8000 make front-dev`.

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
| `LLM_PROVIDER`, `EMBED_PROVIDER` | ml | `stub` — эвристики, ответы `degraded=true`; `yandex` / `ollama` | **работает только `stub`**: провайдеры `yandex` и `ollama` ещё не написаны (ML-03, ML-04), с ними `ml_service` не стартует |
| `YC_FOLDER_ID`, `YC_API_KEY` | ml | YandexGPT и эмбеддинги Яндекса | понадобятся после ML-03 |
| `COLLECTOR_MODE`, `ML_MODE` | search | `grpc` (по умолчанию) — настоящие соседи; `stub` — офлайн-заглушки | `stub` добавляет поиску предупреждение «имитация» |

Локальная LLM без ключей Яндекса (после ML-03/ML-04): `docker compose --profile llm-local up -d ollama`,
затем `LLM_PROVIDER=ollama` для ml_service. На сервере `COLLECTOR_FAKE=false` всегда.

## Как добавить / поменять RPC (контракт — точка синхронизации)

1. Правка `.proto` (и `openapi.yaml`, если меняется HTTP) — через TL.
2. `make proto` → коммит `packages/platform_contracts` и `docs/` (CI проверяет, что всё свежее).
3. Сервис: команда/запрос → хэндлер → регистрация в `dependencies.py` → метод servicer'а → маппер.
4. Ошибка = строка в `ERROR_CODES` (`transport/grpc/errors.py`); gateway отдаёт её код фронту.
5. Gateway: схема в `schemas/`, ручка в `routers/`.
6. `make fmt && make check`.

Пока сценарий не написан, хэндлер бросает `NotImplementedYetError` → gRPC `UNIMPLEMENTED` →
HTTP **501 `NOT_IMPLEMENTED`** с номером задачи в сообщении. Сейчас так отвечают: импорт источников
из XLSX и выгрузка DOCX (B2-10), коннекторы OK / MAX / сайты (B1-04…B1-08).

## Команды

| Команда | Что делает |
|---|---|
| `make install` / `make lock` | `.env` + `uv sync` / `uv lock` в каждом сервисе |
| `make proto` | Python из `contracts/**/*.proto` + `make docs` |
| `make docs` | `docs/API.md`, `docs/api-types.ts`, `docs/GRPC.md` из контрактов |
| `make mock` | Prism-мок HTTP API на :4010 |
| `make up` / `down` / `reset` / `ps` / `logs [s=...]` | Docker |
| `make db` / `make run s=<сервис>` | локальная разработка (Postgres в Docker / сервис из своей папки) |
| `make front-dev` | `npm run dev` на :5173 (прокси `/api` → Prism, если не задан `VITE_API_TARGET`) |
| `make migration s=search_service m="msg"` | миграция alembic (autogenerate) |
| `make fmt` / `lint` / `typecheck` / `test` / `check` | ruff, mypy --strict, pytest (как в CI) |
| `make smoke [URL=...]` | сквозной тест живого стенда |
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
  (search_service соседям его пока не передаёт — B2-12).
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
