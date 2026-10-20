# collector_service

Получение публикаций с площадок. Владелец — B1 (`docs/tasks/B1-collector.md`).
gRPC: `contracts/collector/v1/collector_service.proto` (справочник — `docs/GRPC.md`). Порт 50054. Своей БД нет.

Слои — как в `search_service` (Mediator, CQRS), но без UnitOfWork и Postgres: сервис только читает
с площадок, команд, которые меняют состояние, в нём нет — все четыре запроса это Query.

```
src/collector_service/
  domain/
    enums.py           ← Platform, Health
    value_objects.py   ← Period, PlatformInfo, SourceInfo, RawPost, PostMetrics, CollectResult
    exceptions.py      ← UnsupportedUrl, SourceNotFound, SourcePrivate, PlatformUnavailable, RateLimited
    urls.py            ← ссылка → нормализованная форма, хост, части пути
    services.py        ← finalize_result: общие гарантии (период, дубли, пустой текст, max_posts)
  applications/
    mediator.py        ← Mediator + маркер Command[T] (копия из search_service)
    queries/           ← GetPlatforms, ResolveSource, CollectFromSource, SearchPlatform
    handlers/          ← по одному хэндлеру на запрос
    ports/connectors.py← PlatformConnector и ConnectorRegistry (протоколы)
    exceptions.py      ← InvalidRequest, NotImplementedYet; limits.py, context.py
  infra/
    config.py http.py  ← настройки и общий httpx.AsyncClient
    connectors/        ← vk.py (готов) ok.py max.py news.py (B1-04..B1-08), fake.py, registry.py, base.py
    vk_api/            ← клиент VK API: client.py (ретраи, коды ошибок), limiter.py, transport.py, mapping.py
  transport/grpc/      ← servicer (proto → Query → mediator → proto), mappers, errors (ERROR_CODES), server
  dependencies.py      ← composition root: настройки → коннекторы → реестр → хэндлеры в Mediator
```

Зависимости идут только вниз: `domain ← applications ← infra / transport`. Это проверяет
`tests/test_layering.py`.

Новая площадка = класс в `infra/connectors/` с методами `health / resolve / collect / search` +
строка в `dependencies.build_connectors`. Коннектор возвращает типы из `domain/`, про proto не знает.
Новый RPC = Query в `applications/queries/` + хэндлер в `applications/handlers/` + регистрация в
`dependencies.build_mediator` + метод в servicer (тест `test_every_query_has_a_handler` ловит
забытую регистрацию).

## Как получаем публикации (B1-10)

Сводка для README проекта (TL-08). Правило для всех площадок одно: ссылка, текст, дата и название
источника берутся только из ответа площадки; не открылся пост — в подборку не идёт; нет даты —
`published_at` пустой, а не «сегодня».

| Площадка | Метод | Что нужно | Режимы | Лимиты | Ограничения | Как проверено |
|---|---|---|---|---|---|---|
| ВКонтакте | официальный VK API: `groups.getById`, `wall.get`, `wall.getById`; поиск по всей площадке — только Яндекс `site:vk.com` + `wall.getById` (свой `newsfeed.search` закрыт ключу, 1051) | сервисный ключ VK (`VK_SERVICE_TOKEN`) или токен VK ID (`scripts/vk_token.py`) | источники ✔; по всей площадке — только с ключом Яндекса | 3 запроса/с; стена — до 5000 постов вглубь | посты без текста (только фото/видео) пропускаем | 19.10: живой сервисный ключ — `groups.getById` и `wall.get` отвечают, поиск по каталогу — 55 из 60 источников; `newsfeed.search` — 1051 |
| Одноклассники | публичные страницы групп без входа: страница группы, лента `/group/{id}/topics`, страница топика | ничего | источники ✔; по всей площадке — только через Яндекс `site:ok.ru` | 0,5 запроса/с на ok.ru; лента — до 40 страниц × 20 топиков | время на страницах — московское, переводим в UTC; анти-бот OK может временно закрыть страницы | разбор на настоящих страницах группы НГС (снято 19.10, `tests/fixtures/ok/`); живая сверка 5 постов — `scripts/reliability_check.py` (B1-12) |
| MAX | Bot API: `GET /chats/{handle}`, `GET /messages` | токен бота (`MAX_BOT_TOKEN`); бот — администратор канала | только источники; «везде» невозможно — у Bot API нет поиска, веб без входа пуст | 2 запроса/с; до 30 × 100 сообщений на канал | только каналы, где наш бот — администратор; ссылка на пост может открываться только в приложении MAX | код и тесты на синтетических ответах по dev.max.ru; вживую — B1-11 |
| Новостные сайты | RSS-ленты сайтов из перечня; если в ленте анонс — открываем статью (`NEWS_OPEN_ARTICLES`) | ничего | источники ✔; по всей площадке — свежие ленты всех сайтов перечня | 1 запрос/с на сайт | только то, что сейчас в ленте (обычно последние 1–3 дня), не архив | ленты 4 сайтов открылись при пробе 19.10; разбор — на настоящих лентах НГС24 и АиФ (`tests/fixtures/news/`) |
| Яндекс Search API (необязательно) | поиск по всей площадке VK и OK: выдача → открываем каждую ссылку площадкой | `YC_FOLDER_ID`, `YC_SEARCH_API_KEY` (роль `search-api.webSearch.user`) | — | 5 запросов/с (квота API — 10); 1 платный запрос = до 100 ссылок на фразу | платный; покрытие неполное, свежие посты индексируются с задержкой; дату даёт площадка, не поисковик | код и тесты; на стенде не подключён |

Общие лимиты на один сбор: до `DEFAULT_MAX_POSTS_SOURCE` постов с источника и
`DEFAULT_MAX_POSTS_SEARCH` на поиск «везде» (в Docker — 150 и 200, без Docker — 300 и 500), бюджет
**50 с** (`COLLECT_BUDGET_SECONDS`): search_service ждёт цель 60 с, сборщик заканчивает раньше и
отдаёт то, что успел, с `truncated` и предупреждением. Карточка источника по ссылке кэшируется на 10 минут.

### Тексты ошибок (B1-13)

Текст ошибки сборщика search_service показывает сотруднику как есть, поэтому в нём нет кодов HTTP,
`rpc error`, названий методов и переменных окружения. Подробность (статус, ответ площадки, что
проверить) лежит в `CollectorError.detail` и попадает только в лог — строка `… failed in …` или
`сбор прерван …`. Все тексты — `domain/messages.py`, тест — `tests/test_error_texts.py`.

| Ситуация | Что видит сотрудник |
|---|---|
| Яндекс отклонил ключ (401/403) | «Поиск по всей площадке временно недоступен (сервис поиска отклонил доступ). Поиск по вашим источникам работает» |
| Ключ Яндекса не задан | «Поиск по всей площадке не настроен. Поиск по вашим источникам работает» |
| VK 1051 (`newsfeed.search` закрыт ключу) | не ошибка: по умолчанию метод не вызываем; с ключом Яндекса — заметка «ВКонтакте: Поиск «везде» — через Яндекс, …» |
| Таймаут, сеть, 5xx площадки | «{Площадка}: площадка не ответила, повторите позже» |
| Некорректный id источника (`verify_…`) | «{Площадка}: источник не найден на площадке — проверьте ссылку» |
| Ключ площадки не принят / истёк | «{Площадка}: ключ доступа недействителен — обратитесь к администратору» |
| 403 / страница «не робот» (OK, сайты) | «{Площадка}: площадка временно ограничила доступ (проверка «не робот»), повторите позже» |

Новая ошибка: текст сотруднику — первым аргументом, техника — в `detail=`:
`raise PlatformUnavailableError(messages.no_answer("MAX"), detail=f"MAX: HTTP {status}")`.

### Поиск «везде» по VK и ошибка 1051 (B1-14)

`newsfeed.search` отвечает ошибкой 1051 («метод недоступен для этого типа ключа») и сервисному
ключу, и токену VK ID. Поэтому по умолчанию (`VK_NEWSFEED_SEARCH=false`) сборщик его не вызывает,
а `GetPlatforms` честно отдаёт VK `global_mode=false`: search_service не создаёт цель «поиск по всей
площадке», и «Везде» во VK — все активные источники каталога.

С ключом Yandex Search API (`YC_SEARCH_API_KEY`) поиск по всей площадке VK включается сам: Яндекс
`site:vk.com`, каждую ссылку выдачи открываем через `wall.getById` и берём текст и дату из ответа
VK (`WithSearchFallback`). Минусы: платно, свежие посты индексируются с задержкой, покрытие меньше.
Ключ, которому `newsfeed.search` открыт (классическое Standalone-приложение), — `VK_NEWSFEED_SEARCH=true`:
сборщик сначала пробует свой поиск VK. Для слайда «Ограничения»: «VK закрыл поиск для ключей
приложений, „Везде“ — наш каталог источников края».

### Новостные сайты (B1-15)

Перечень — настройка `NEWS_SITES`, по умолчанию (`infra/config.py`):

| Сайт | Лента | Текст в ленте |
|---|---|---|
| НГС24 | `https://ngs24.ru/rss-feeds/rss.xml` | анонс → открываем статью (проверено на ленте от 19.10) |
| Newslab.ru | `https://newslab.ru/news/all/rss` | не сверяли |
| АиФ-Красноярск | `https://krsk.aif.ru/rss/all.php` | полный текст (проверено на ленте от 19.10) |
| Сибирское агентство новостей | `https://sibnovosti.ru/rss/` | не сверяли |

При пробе 19.10 ленты не открылись у gornovosti.ru, prmira.ru, krsk.kp.ru, dela.ru, 7kanal.com,
tvk6.ru — их в перечне нет. Полный ли текст в ленте или анонс, решает разбор ленты: анонс короче
400 знаков — открываем статью и берём текст со страницы (`NEWS_OPEN_ARTICLES=false` — не открывать).

**Добавить сайт без правки кода:** в `.env` (локально — `services/collector_service/.env`, на сервере
— в окружении перед `make deploy`) записать весь перечень, включая старые сайты:

```
NEWS_SITES='ngs24.ru|https://ngs24.ru/rss-feeds/rss.xml|НГС24; newslab.ru|https://newslab.ru/news/all/rss|Newslab.ru; krsk.aif.ru|https://krsk.aif.ru/rss/all.php|АиФ-Красноярск; sibnovosti.ru|https://sibnovosti.ru/rss/|Сибирское агентство новостей; новый-сайт.ru|https://новый-сайт.ru/rss|Новый сайт'
```

затем `docker compose up -d collector_service`. Проверить ленту:
`uv run python scripts/live_check.py новый-сайт.ru` — должны появиться посты с датами и ссылками;
в «Площадки» у новостных сайтов «RSS-ленты N из N сайтов».

### Сверка достоверности (B1-12)

```
cd services/collector_service
uv run python scripts/reliability_check.py            # 5 постов VK + 5 постов OK из seed → docs/demo/reliability-check.md
python scripts/record_ok_fixtures.py                  # настоящие страницы 3 групп OK → tests/fixtures/ok/real/
VK_SERVICE_TOKEN=... python scripts/record_vk_fixtures.py news_ngs24 "ДТП Красноярск"
uv run pytest tests/test_ok_real_fixtures.py tests/test_vk_real_fixtures.py
```

`reliability_check.py` собирает посты тем же кодом, что сервис, и сам перепроверяет каждый вторым
путём (OK — страница топика, VK — `wall.getById`): совпали ли текст и дата. В таблице остаются
три колонки для человека — открыть ссылку в браузере без входа и отметить. Даты в таблице — по
Красноярску (как в интерфейсе) и по Москве (как на страницах OK).

### MAX в Docker (B1-11)

`MAX_BOT_TOKEN`, `MAX_API_URL`, `HTTP_CA_BUNDLE` пробрасываются в контейнер (`compose.yaml`, на
сервере — `env.j2`). Если в логе `CERTIFICATE_VERIFY_FAILED` при обращении к MAX — положить корневой
сертификат Минцифры в `infra/certs/` (см. `infra/certs/README.md`). Старый домен API
Адрес по умолчанию — `platform-api2.max.ru` (старый `platform-api.max.ru` закрыт). Для TLS нужен корневой сертификат Минцифры: он лежит в `infra/certs/russian_trusted_root_ca.pem`, в `.env` — `HTTP_CA_BUNDLE=/certs/russian_trusted_root_ca.pem`.

### Скорость сбора (B1-16)

Сколько длился каждый сбор, сборщик пишет в лог строкой `<площадка>:<источник> … spent=12.3s`:
`docker compose logs collector_service | grep spent=`. Оценка до замеров: OK при 0,5 запроса/с —
страница ленты (20 топиков) раз в 2 с, неделя активной группы (~150 постов) ≈ 8 страниц ≈ 16–20 с;
VK — 1–3 запроса на источник, секунды; сайты — один запрос ленты + статьи с анонсами по 1/с на сайт.

## ВКонтакте (B1-03, health — часть B1-07)

Нужен сервисный ключ: `VK_SERVICE_TOKEN` в `.env`. Без него `GetPlatforms` честно отвечает
`UNAVAILABLE: Не настроен доступ`, остальные вызовы — `PLATFORM_UNAVAILABLE`.

| Режим | Как получаем |
|---|---|
| `ResolveSource` | `groups.getById` для `vk.com/имя`, `club123`, `public123`, `event123`, `vk.ru`, `m.vk.com`. Страница человека (`vk.com/id1`) — `UNSUPPORTED_URL` |
| `CollectFromSource` | `wall.get` по 100 постов, пока посты не станут старше начала периода; закреплённый старый пост на это не влияет |
| `SearchPlatform` | `newsfeed.search` по каждой фразе (до 200 за страницу, VK отдаёт не больше ~1000 на фразу), дубли между фразами схлопываются |

- Текст репоста = свой текст + `\n\n` + текст оригинала; посты без текста пропускаются и считаются в `warnings`.
- Метрика, которой нет в ответе VK, остаётся пустой (не 0); дата — только из `date`.
- Коннектор **не** сужает по региону и **не** фильтрует по `keywords`: фразы приходят от ML как есть,
  ищем по всему открытому VK. Привязка к региону и отбор по смыслу — ML и `search_service`.
- Лимит ≈3 запроса/с (`VK_REQUESTS_PER_SECOND`), ретраи с паузой на ошибки VK 6 и 10, до 4 попыток.
  Ошибки VK: 5 → `PLATFORM_UNAVAILABLE`, 15/18/30 → `SOURCE_PRIVATE`, 100/113 → `SOURCE_NOT_FOUND`,
  6/9/29 после ретраев → `RATE_LIMITED`, 1051 → запасной путь через Яндекс (см. B1-14 выше).
  Токен передаётся в теле POST и в логи не попадает.
- Health: запрос `users.get` с ключом, «здорова» кэшируется на 5 минут, проблема — на 1 минуту.

### Fixtures и сверка с живым VK

`tests/fixtures/vk/*.json` — **синтетические** (составлены по документации VK, подписаны ключом
`_synthetic`). Они проверяют нашу логику, но не то, что VK отвечает именно так. Настоящие ответы:

```
cd services/collector_service
VK_SERVICE_TOKEN=... python scripts/record_vk_fixtures.py krsk_news "ДТП Красноярск"   # только stdlib
uv run pytest tests/test_vk_real_fixtures.py
```

Скрипт кладёт ответы в `tests/fixtures/vk/real/` (без токена); пока их нет, этот тест пропускается.
