# B1 — collector_service («парсинг»)

Зона: `services/collector_service/**`. Контракт: `contracts/collector/v1/collector_service.proto` (порт 50054).
Своей БД нет. Твоя задача — **реальные посты с реальными ссылками** с трёх площадок. Это 5 баллов
«Поддержка площадок» + основа 10 баллов «Достоверность». Каждая площадка, которая реально работает
на демо, — +1–2 балла; заранее внесённые карточки и сгенерированные ссылки = 0.

**Где смотреть поля и типы:** [`docs/GRPC.md` → пакет `collector.v1`](../GRPC.md#collectorv1collectorservice),
первоисточник — `contracts/collector/v1/collector_service.proto`, общие типы `Platform`, `Period`,
`ErrorInfo` — [`common.v1`](../GRPC.md#commonv1platform). Устройство сервиса (слои domain → applications →
infra / transport, Mediator, как добавить площадку) — [`services/collector_service/README.md`](../../services/collector_service/README.md).

**Золотое правило:** всё, что ты возвращаешь в `RawPost`, взято из ответа площадки. Нет даты — поле
не заполнено. Нет текста — пост не возвращаем. Ссылку строишь из id (каноничная форма), а не копируешь.

## Старт после pull

```bash
cd services/collector_service
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q
#   тесты VK — на СИНТЕТИЧЕСКИХ ответах (tests/fixtures/vk/*.json), без сети; test_vk_real_fixtures пропускается
GRPC_ADDRESS=127.0.0.1:50054 COLLECTOR_FAKE=true uv run collector-service
grpcurl -plaintext 127.0.0.1:50054 list
grpcurl -plaintext -d '{"url":"vk.com/krsk_news"}' 127.0.0.1:50054 collector.v1.CollectorService/ResolveSource
```

PowerShell: `$env:GRPC_ADDRESS="127.0.0.1:50054"; $env:COLLECTOR_FAKE="true"; uv run collector-service`.

Настоящие площадки: `COLLECTOR_FAKE=false VK_SERVICE_TOKEN=<ключ> uv run collector-service`. Без ключа
`GetPlatforms` отвечает VK `UNAVAILABLE` «не настроен доступ», вызовы — `PLATFORM_UNAVAILABLE`; OK / MAX /
сайты — `UNIMPLEMENTED` (через gateway — 501). Весь стенд с твоим сервисом — вариант Б из
[README](../../README.md#быстрый-старт-после-pull) с `COLLECTOR_FAKE=false`.

## Что изменилось при сборке `main`

Твоя ветка `b1/layers-and-vk-connector` слита без изменений в коде сборщика. Новое для тебя: сервис
впервые работает в цепочке — search_service ходит в него по gRPC (`ResolveSource` при добавлении
источника, `CollectFromSource` по `external_id` источника, `SearchPlatform` с фразами от ML), gateway —
за `/platforms`. На `COLLECTOR_FAKE=true` вся цепочка проходит; с настоящим VK — ни разу (нет ключа).

---

### [ ] B1-01 · P0 · H+0 → H+3 (жёсткий дедлайн) · spike OK и MAX — **главный риск проекта**
> Сделано: [`docs/collector-spike.md`](../collector-spike.md) — по документации, живых запросов к ok.ru /
> max.ru не было; `scripts/spike_probe.py` для проб. Если H+3 прошёл — это сейчас твоя задача № 1:
> от неё зависят B1-04, B1-05, B1-06.

**Сделать (с машины, где есть сеть до ok.ru и max.ru):**
1. Из `services/collector_service`: `python scripts/spike_probe.py --save https://ok.ru/group/<id>/topics https://m.ok.ru/group/<id>/topics https://max.ru/<канал>`
   (только stdlib; или из корня репозитория: `SPIKE_URLS="…" bash scripts/diagnose.sh`) — ответы лягут в
   `tests/fixtures/spike/`.
2. По каждому «?» в разделе 3 spike — ответ: отдаётся ли HTML без логина, есть ли текст / дата / id поста,
   как листать, анти-бот; MAX — есть ли посты в SSR / `__data.json`; Yandex Search API — принимает ли
   `site:ok.ru` в `queryText` (один запрос, ключ — TL-04).
3. 10 минут с TL: решение по каждой площадке × режиму, записать в таблицу §1 spike.

**DoD.** Для OK и MAX есть хоть один реально полученный пост со ссылкой, которая открывается в
браузере, — или честная запись «не получается, показываем так-то».

### [x] B1-02 · P0 · к H+3 · стаб сервиса по контракту
> Сделано: `infra/connectors/fake.py` — посты `[FAKE]`, детерминированные (повторный сбор даёт те же
> посты), особые `external_id` `fail` / `empty` / `closed`; общие гарантии (период, дубли, пустой текст,
> `max_posts`) — `domain/services.py`. Работает в сквозном прогоне через gateway.

### [ ] B1-03 · P0 · к H+10 · коннектор VK — ⌛ ждёт ключа
> Сделано: `infra/connectors/vk.py` + `infra/vk_api/` — resolve (`groups.getById` для `vk.com/имя`, `club`,
> `public`, `event`, `vk.ru`, `m.vk.com`), collect (`wall.get` до начала периода, закреплённый пост не
> останавливает), search (`newsfeed.search` по каждой фразе, дубли схлопываются), лимитер ≈3 запроса/с,
> ретраи на 6/10, коды ошибок VK → коды контракта, токен не попадает в логи. Тесты — на синтетических ответах.

**Осталось (как только TL-04 даст ключ):**
1. Из `services/collector_service`: `VK_SERVICE_TOKEN=… python scripts/record_vk_fixtures.py krsk_news "ДТП Красноярск"` →
   `tests/fixtures/vk/real/`, затем `uv run pytest tests/test_vk_real_fixtures.py` — тест перестанет
   пропускаться. Где синтетика разошлась с реальностью — поправить маппинг.
2. Сверка руками: 3 группы края за 14 дней, 5 ссылок открываются и совпадают с vk.com (текст, дата).
3. Весь стенд с `COLLECTOR_FAKE=false`: `make smoke URL=http://127.0.0.1:8000` (smoke сам возьмёт
   `vk.com/krsk_news`) и поиск «ДТП Красноярск» в UI — посты с рабочими ссылками.
4. Время: search_service ждёт одну цель 60 с. Замерить `wall.get` за 30 дней у крупной группы и
   `newsfeed.search` по 5 фразам; если не укладывается — B1-09 п. 2.

**DoD.** Для 3 реальных групп края за 14 дней посты совпадают с тем, что видно на vk.com (5 ссылок
сверены); `newsfeed.search("ДТП Красноярск")` даёт посты с рабочими ссылками.

### [ ] B1-04 · P0 · к H+20 · коннектор OK
**Где:** `infra/connectors/ok.py` (сейчас `NotImplementedConnector` → `UNIMPLEMENTED` «B1-04»; уже
подключён в `dependencies.build_connectors`). Контракт тот же, что у VK (`SourceInfo`, `RawPost` — справка ниже).
Таблицу «поле `RawPost` ← откуда на странице OK» записать в `docs/collector-spike.md` до начала кода:
`source_external_id` = gid группы, `post_external_id` = id топика, `title` — не заполнять.
Способ — по решению B1-01. Требования: resolve, collect за период, каноничная ссылка
`https://ok.ru/group/{gid}/topic/{tid}`, дата (если на странице «вчера в 14:05» — парсить относительно
часового пояса, в котором показывает OK, и записать в README сервиса, как трактуем), текст без HTML.
Парсер HTML — `selectolax`; при анти-боте — пауза, ротацию не делаем. Fixtures из B1-01 + тесты. `health()` —
запрос к известной странице, кэш 5 минут (как у VK).

**DoD.** Как B1-03 для 2–3 групп OK.

### [ ] B1-05 · P0 · к H+22 · коннектор MAX
**Где:** `infra/connectors/max.py` (сейчас заглушка «B1-05»). Таблица соответствия полей MAX → `RawPost` — в
`docs/collector-spike.md`. `source_external_id` — стабильный id канала (не handle, если handle можно
сменить; если другого нет — handle). Способ — по решению B1-01. Минимум для баллов: посты канала из списка
с текстом, датой (если есть) и прямой ссылкой на пост. Учесть soft-лимит по IP: кэш, паузы, ясная ошибка
`RATE_LIMITED`. Если глобального поиска по MAX нет — `global_mode_supported=false` и честный `note`.

**DoD.** Как B1-03 для 2–3 каналов MAX.

### [ ] B1-06 · P0 · к H+24 · глобальный поиск OK / MAX (если spike подтвердил)
Yandex Search API (`YC_FOLDER_ID`, `YC_SEARCH_API_KEY` уже есть в `Settings`): `"<фраза>" site:ok.ru`
(и `site:max.ru`); произвольный период API не задаёт (только 1 день / 2 недели / месяц) — отбор по дате
после открытия страницы. **Каждую ссылку открыть** через коннектор площадки и достать текст и дату со
страницы. Не открылась / не пост (а группа, профиль) — выкинуть. В `note` площадки — «поиск через Яндекс —
покрытие неполное». Цена — 488 ₽ за 1000 запросов (spike §2.3): посчитать на типичный поиск для README.

**DoD.** Глобальный поиск по OK возвращает только посты, чьи ссылки открываются и чей текст совпадает.

### [x] B1-07 · P0 · к H+12 · GetPlatforms и здоровье
> Сделано: по записи на VK, OK, MAX, сайты; VK — `users.get` с ключом, «здорова» кэшируется 5 минут,
> проблема — 1 минуту; нет ключа → `UNAVAILABLE` «не настроен доступ»; неподключённые площадки →
> `UNAVAILABLE` «Площадка ещё не подключена»; при `COLLECTOR_FAKE=true` — пометка «ТЕСТОВЫЕ данные».
> Здоровье OK и MAX — часть B1-04 / B1-05.

### [ ] B1-08 · P1 · к H+32 · новостные сайты (доп. возможность)
`infra/connectors/news.py` (заглушка). Перечень сайтов из стартовых материалов. RSS (`feedparser`) или
sitemap → статья по ссылке → `trafilatura` для текста. `title` — заголовок статьи, дата — из RSS /
`article:published_time`. `Platform.NEWS`, `source_mode` по сайтам из каталога.

### [ ] B1-09 · P1 · по ходу · надёжность
> Сделано: таймаут HTTP 15 с, лимитер VK, логи по источнику «получено / оставлено / без текста / вне
> периода / обрезано» с `request_id` и без текстов.

**Осталось.**
1. Кэш resolve на 10 минут (сейчас каждый resolve — запрос к площадке).
2. Бюджет на цель: search_service обрывает цель через 60 с и считает её упавшей. Сборщик должен сам
   остановиться раньше (≈50 с) и вернуть то, что успел, с `truncated` / warning, а не падать.
3. Лимитер на хост для OK / MAX (вместе с B1-04 / B1-05).

### [ ] B1-10 · P0 · к H+36 · раздел README «Как получаем публикации»
По каждой площадке: способ (API / страницы / поиск), какие данные берём, лимиты, что не поддерживается,
какие доступы нужны и где они настроены. Основа — раздел «ВКонтакте» в README сервиса и
`docs/collector-spike.md`. Отдать TL (TL-08).

---

## Контракт (справка)

| RPC | Запрос | Ответ | Ошибки (`ERROR_CODES`) |
|---|---|---|---|
| `GetPlatforms` | `{context}` | `{platforms: PlatformInfo[]}` | — |
| `ResolveSource` | `{context, url: str}` | `{source: SourceInfo}` | `UNSUPPORTED_URL`→`INVALID_ARGUMENT`, `SOURCE_NOT_FOUND`→`NOT_FOUND`, `SOURCE_PRIVATE`→`FAILED_PRECONDITION`, `PLATFORM_UNAVAILABLE`→`UNAVAILABLE` |
| `CollectFromSource` | `{context, platform, source_external_id, period, keywords, max_posts}` | `{posts: RawPost[], truncated, warnings}` | те же + `RATE_LIMITED`→`RESOURCE_EXHAUSTED` |
| `SearchPlatform` | `{context, platform, queries, period, region_terms, max_posts}` | `{posts: RawPost[], truncated, warnings}` | `PLATFORM_UNAVAILABLE`, `RATE_LIMITED` |

```
Period       { start: Timestamp, end: Timestamp }          // UTC, включительно (search_service уже перевёл из Красноярска)
PlatformInfo { platform, title, source_mode_supported, global_mode_supported, health (OK|DEGRADED|UNAVAILABLE), note }
SourceInfo   { platform, external_id, screen_name, url, name, optional city, optional members_count, is_closed }
RawPost      { platform, source_external_id, source_name, source_url, post_external_id, url (каноничная),
               optional title, text (без HTML, не пустой), optional published_at (нет даты → НЕ заполнять),
               metrics { optional views, likes, reposts, comments }, is_repost, optional repost_of_url, fetched_at }
```

Как тебя вызывает search_service: `CollectFromSource(max_posts=300, keywords=фразы ML)`,
`SearchPlatform(max_posts=500, queries=фразы ML, region_terms=["Красноярск", "Красноярский край"])`,
таймаут 60 с на цель. `keywords` и `region_terms` — подсказки, не условия: регион и смысл оценивают ML и
search_service.

## Интеграция: от кого ты зависишь и кто ждёт тебя

| Что | Связь |
|---|---|
| Ключ VK, ключ Yandex Search API | ждёшь от TL (TL-04) |
| Реальные посты VK | ждут B2 (боевой прогон, B2-11), ML (реальные посты в eval, ML-02), TL (seed, TL-06; демо) |
| OK / MAX | 5 баллов «Площадки»; пока они 501, поиск «везде» по ним — «не удалось» в «Где искали» |
