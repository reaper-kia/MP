# B1 — collector_service («парсинг»)

Зона: `services/collector_service/**`. Контракт: `contracts/collector/v1/collector_service.proto`.
Своей БД нет. Твоя задача — **реальные посты с реальными ссылками** с трёх площадок. Это 5 баллов
«Поддержка площадок» + основа 10 баллов «Достоверность». Каждая площадка, которая реально работает
на демо, — +1–2 балла; заранее внесённые карточки и сгенерированные ссылки = 0.

**Где смотреть поля и типы:** [`docs/GRPC.md` → пакет `collector.v1`](../GRPC.md#collectorv1collectorservice)
(все сообщения с типами и комментариями), первоисточник — `contracts/collector/v1/collector_service.proto`,
общие типы `Platform`, `Period`, `ErrorInfo` — [`common.v1`](../GRPC.md#commonv1platform). В задачах ниже
нужные поля выписаны прямо в тексте.

**Золотое правило:** всё, что ты возвращаешь в `RawPost`, взято из ответа площадки. Нет даты — поле
не заполнено. Нет текста — пост не возвращаем. Ссылку строишь из id (каноничная форма), а не копируешь.

Структура внутри сервиса (CQRS шаблона тут избыточен — делай проще):

```
collector_service/
  connectors/
    base.py          ← Protocol PlatformConnector: resolve(url), collect(src, period, keywords, max),
                       search(queries, period, region_terms, max), health()
    vk.py  ok.py  max.py  news.py  fake.py
    registry.py      ← Platform → connector; fake подменяет всё при COLLECTOR_FAKE=true
  errors.py          ← UnsupportedUrl, SourceNotFound, SourcePrivate, PlatformUnavailable, RateLimited
  http.py            ← общий httpx.AsyncClient: таймауты, ретраи, User-Agent, лимитер на хост
  transport/grpc/    ← servicer: proto ⇄ вызов коннектора; ERROR_CODES
tests/fixtures/      ← сохранённые реальные ответы площадок (json/html) — тесты без сети
```

---

### [ ] B1-01 · P0 · H+0 → H+3 (жёсткий дедлайн) · spike OK и MAX
**Цель.** За 3 часа понять, **как реально** получить посты OK и MAX: текст, дата, прямая ссылка — для
(а) конкретной группы/канала и (б) поиска по площадке. Это главный технический риск проекта.

**Проверить (каждый пункт — 20–30 минут, не залипать):**
- **OK, публичные страницы:** `https://ok.ru/group/<id>/topics`, `https://m.ok.ru/group/<id>/topics`,
  страница отдельного топика. Отдаётся ли HTML без логина, есть ли там текст, дата, id топика,
  как листать вглубь (параметры пагинации/`st.cmd`). Анти-бот, капча?
- **OK, API:** что нужно для `group.getInfo` / ленты группы (регистрация приложения, права
  GROUP_CONTENT, сроки одобрения). Если одобрение > 1 дня — сразу отбрасываем.
- **MAX, веб:** страница `https://max.ru/<handle>` — есть ли в HTML/SSR последние посты; `__data.json`
  (известно, что отдаёт метаданные канала, лимит по IP, формат менялся); ссылки на отдельный пост —
  какой формат; есть ли дата.
- **MAX, Bot API** (`platform-api2.max.ru`, токен через business.max.ru): читает ли он каналы, где бот
  не админ. Скорее всего нет — тогда режим «бот добавлен в канал» как запасной.
- **Глобальный поиск OK/MAX:** Yandex Search API с `site:ok.ru` / `site:max.ru` + фраза + период —
  возвращает ли ссылки на конкретные посты.
- **VK для сверки:** `newsfeed.search` и `wall.get` с сервисным ключом — работают ли (5 минут).

**Результат.** `docs/collector-spike.md`: таблица «площадка × режим → способ, пример запроса, что
получаем (текст/дата/ссылка), ограничения, риск» + 2–3 сохранённых реальных ответа в `tests/fixtures/`.
На H+3 — 10 минут с TL, решение по каждой площадке. Если для MAX/OK нет ничего рабочего — фиксируем
честно и решаем, что показываем (например, MAX только по каналам из списка через веб-страницу).

**DoD.** Решение принято и записано; для каждой площадки есть хоть один реально полученный пост
со ссылкой, которая открывается в браузере.

### [x] B1-02 · P0 · к H+3 · стаб сервиса по контракту
> Сделано в каркасе: `connectors/fake.py` (тестовые посты [FAKE], `fail` / `empty` / `closed`),
> гарантии сервиса (период, дубли, max_posts) — `service.py`. Остаётся: реальные коннекторы B1-03…B1-08.
**Цель.** B2 начинает интеграцию, не дожидаясь настоящих коннекторов.

**Сделать.** Все 4 RPC отвечают. `fake.py` читает `tests/fixtures/fake_posts.json` (20–30
правдоподобных постов разных площадок, **в тексте явно `[FAKE]`**), фильтрует по периоду, имитирует
задержку 1–3 с и ошибку для source_external_id `"fail"` (`PLATFORM_UNAVAILABLE`) — чтобы B2 и FE
отладили сценарий 5. Включается только `COLLECTOR_FAKE=true`. `GetPlatforms` при fake пишет в `note`
«ТЕСТОВЫЕ ДАННЫЕ».

**Контракт** — `service CollectorService` (порт 50054):

| RPC | Запрос | Ответ | Ошибки (`ERROR_CODES`) |
|---|---|---|---|
| `GetPlatforms` | `{context}` | `{platforms: PlatformInfo[]}` | — |
| `ResolveSource` | `{context, url: str}` | `{source: SourceInfo}` | `UNSUPPORTED_URL`→`INVALID_ARGUMENT`, `SOURCE_NOT_FOUND`→`NOT_FOUND`, `SOURCE_PRIVATE`→`FAILED_PRECONDITION`, `PLATFORM_UNAVAILABLE`→`UNAVAILABLE` |
| `CollectFromSource` | `{context, platform: Platform, source_external_id: str, period: Period, keywords: str[], max_posts: uint32}` | `{posts: RawPost[], truncated: bool, warnings: str[]}` | те же + `RATE_LIMITED`→`RESOURCE_EXHAUSTED` |
| `SearchPlatform` | `{context, platform: Platform, queries: str[], period: Period, region_terms: str[], max_posts: uint32}` | `{posts: RawPost[], truncated: bool, warnings: str[]}` | `PLATFORM_UNAVAILABLE`, `RATE_LIMITED` |

```
Period       { start: Timestamp, end: Timestamp }          // UTC, включительно (B2 уже перевёл из Красноярска)
PlatformInfo { platform: Platform, title: str, source_mode_supported: bool, global_mode_supported: bool,
               health: PlatformHealth (OK|DEGRADED|UNAVAILABLE), note: str }
SourceInfo   { platform, external_id: str, screen_name: str, url: str, name: str,
               optional city: str, optional members_count: int64, is_closed: bool }
RawPost      { platform, source_external_id: str, source_name: str, source_url: str,
               post_external_id: str, url: str,             // каноничная прямая ссылка
               optional title: str,                         // только если площадка отдаёт заголовок
               text: str,                                   // полный текст без HTML; пустым не бывает
               optional published_at: Timestamp,            // нет даты → НЕ заполнять
               metrics: PostMetrics { optional views, likes, reposts, comments: int64 },
               is_repost: bool, optional repost_of_url: str, fetched_at: Timestamp }
```

Python (сгенерированный код — `from collector.v1 import collector_service_pb2 as pb`):
```python
post = pb.RawPost(platform=common_pb.PLATFORM_VK, source_external_id="-123", post_external_id="456",
                  url="https://vk.com/wall-123_456", text=text, source_name=name, source_url=src_url,
                  is_repost=False)
if dt is not None:
    post.published_at.FromDatetime(dt)          # dt — aware UTC datetime
if views is not None:
    post.metrics.views = views                  # optional: не присвоили → HasField("views") == False
post.fetched_at.GetCurrentTime()
start = req.period.start.ToDatetime(tzinfo=UTC)  # чтение периода
```

**DoD.** `grpcurl … CollectFromSource` возвращает посты; `source_external_id="fail"` → ошибка с кодом.

### [ ] B1-03 · P0 · к H+10 · коннектор VK
**Цель.** Первая реальная площадка. На ней строится MVP-1.

**Контракт.** `ResolveSource` → `SourceInfo`, `CollectFromSource` / `SearchPlatform` → `RawPost[]` — поля
в B1-02 и [GRPC.md#collectorv1rawpost](../GRPC.md#collectorv1rawpost). Соответствие VK → `RawPost`:

| `RawPost` | VK API (`wall.get` / `newsfeed.search` item) |
|---|---|
| `source_external_id` | `owner_id` строкой (`"-12345678"`; пользователь — положительный) |
| `post_external_id` | `id` строкой |
| `url` | `f"https://vk.com/wall{owner_id}_{id}"` |
| `text` | `text` + `"\n\n"` + `copy_history[0].text` (если репост) |
| `published_at` | `date` (unix, UTC) |
| `metrics` | `views.count`, `likes.count`, `reposts.count`, `comments.count` (нет ключа → не заполнять) |
| `is_repost` / `repost_of_url` | `bool(copy_history)` / `wall{copy_history[0].owner_id}_{copy_history[0].id}` |
| `source_name` / `source_url` | из `groups.getById` (`name`, `https://vk.com/{screen_name}`) |
| `title` | не заполнять (у постов VK нет заголовка) |

**Сделать.**
1. **resolve:** принимает `vk.com/krsk_news`, `https://vk.com/club123`, `public123`, `vk.ru/...`,
   `m.vk.com/...` → `groups.getById(fields=city,members_count,is_closed)` → `external_id = -<id>`,
   `screen_name`, `name`, `city`. Мусор → `UnsupportedUrl`; нет группы → `SourceNotFound`.
2. **collect:** `wall.get(owner_id, count=100, offset)` в цикле, пока посты новее начала периода
   (учесть, что закреплённый пост идёт первым и может быть старым — не останавливаться на нём).
   Отбор по периоду. Текст = `text` + текст `copy_history` (репост, `is_repost=true`,
   `repost_of_url`). Посты без текста (только фото/видео) — пропускать, считать в `warnings`.
   `url = https://vk.com/wall{owner_id}_{id}`. Метрики: views/likes/reposts/comments → `PostMetrics`
   (нет поля — не заполнять). `max_posts` по умолчанию 300 → `truncated`.
   Можно ускорить через `execute` (до 25 вызовов в одном).
3. **search:** `newsfeed.search(q, start_time, end_time, count=200, start_from)` по каждой фразе
   (до ~1000 на фразу — лимит VK), объединить, убрать дубли по `(owner_id, id)`. `source_name`
   для найденных — подтянуть пачкой `groups.getById` / `users.get`. Посты от пользователей (owner_id > 0)
   — оставлять, `source_name` = имя.
4. Лимитер ≈ 3 запроса/с на ключ, ретрай на ошибке 6 (too many requests) и 10 (internal) с бэкоффом.
   Ошибки VK → коды: 5 → `PLATFORM_UNAVAILABLE`, 15/18/30 → `SOURCE_PRIVATE`, 100/113 → `SOURCE_NOT_FOUND`.
5. Тесты на сохранённых ответах VK (fixtures), без сети.

**DoD.** Для 3 реальных групп края за 14 дней посты совпадают с тем, что видно на vk.com (сверить 5
ссылок руками); `newsfeed.search("ДТП Красноярск")` даёт посты с рабочими ссылками.

### [ ] B1-04 · P0 · к H+20 · коннектор OK
**Контракт** — тот же, что в B1-02/B1-03 (`SourceInfo`, `RawPost`). Таблицу «поле `RawPost` ← откуда на
странице OK» (как у VK в B1-03) записать в `docs/collector-spike.md` до начала кода: `source_external_id`
= gid группы, `post_external_id` = id топика, `title` — не заполнять (у топика нет заголовка).
Способ — по решению B1-01. Те же требования: resolve, collect за период, каноничная ссылка
`https://ok.ru/group/{gid}/topic/{tid}`, дата (если на странице «вчера в 14:05» — парсить относительно
Asia/Krasnoyarsk/Moscow, как отображает OK, и записать в README, как трактуем), текст без HTML.
Парсер HTML — `selectolax`; при анти-боте — пауза, ротация не делаем. Fixtures + тесты.

**DoD.** Как B1-03 для 2–3 групп OK.

### [ ] B1-05 · P0 · к H+22 · коннектор MAX
**Контракт** — тот же (`SourceInfo`, `RawPost`); таблица соответствия полей MAX → `RawPost` — в
`docs/collector-spike.md`. `source_external_id` — стабильный id канала (не handle, если handle можно
сменить; если другого нет — handle). Способ — по решению B1-01. Минимум для баллов: посты канала из списка с текстом, датой (если есть)
и прямой ссылкой на пост. Учесть soft-лимит по IP: кэш, паузы, ясная ошибка `RATE_LIMITED`.
Если глобального поиска по MAX нет — `global_mode_supported=false` и честный `note`.

**DoD.** Как B1-03 для 2–3 каналов MAX.

### [ ] B1-06 · P0 · к H+24 · глобальный поиск OK / MAX (если spike подтвердил)
Yandex Search API: `"<фраза>" site:ok.ru` (и `site:max.ru`), период — фильтр API, если есть, иначе
отбор по дате после загрузки. **Каждую ссылку открыть** через коннектор площадки и достать текст и
дату со страницы. Не открылась / не пост (а группа, профиль) — выкинуть. Пометить в `note` площадки
«поиск через Яндекс — покрытие неполное».

**DoD.** Глобальный поиск по OK возвращает только посты, чьи ссылки открываются и чей текст совпадает.

### [ ] B1-07 · P0 · к H+12 · GetPlatforms и здоровье
**Контракт.** `GetPlatformsResponse { platforms: PlatformInfo[] }` — по одной записи на `PLATFORM_VK`,
`PLATFORM_OK`, `PLATFORM_MAX`, `PLATFORM_NEWS` (если B1-08 не сделан — `health=UNAVAILABLE`, `note`
«не подключено»). `title`: «ВКонтакте», «Одноклассники», «MAX», «Новостные сайты».
Кэш 5 минут: VK — дешёвый запрос с ключом; OK/MAX — запрос к известной странице. `health` →
`OK / DEGRADED / UNAVAILABLE` + понятный `note` по-русски. Нет ключа в `.env` → `UNAVAILABLE`
«не настроен доступ».

### [ ] B1-08 · P1 · к H+32 · новостные сайты (доп. возможность)
Перечень сайтов из стартовых материалов. RSS (`feedparser`) или sitemap → статья по ссылке →
`trafilatura` для текста. `title` — заголовок статьи, дата — из RSS/`article:published_time`.
`Platform.NEWS`, `source_mode` по сайтам из каталога.

### [ ] B1-09 · P1 · по ходу · надёжность
Таймаут на запрос 15 с, на цель — укладываться в 30–60 с (отдавать что успел + `truncated`/warning,
а не падать). Кэш resolve 10 мин. Лимитер на хост. Логи: площадка, источник, сколько получили,
сколько выкинули и почему (без текстов).

### [ ] B1-10 · P0 · к H+36 · раздел README «Как получаем публикации»
По каждой площадке: способ (API/страницы/поиск), какие данные берём, лимиты, что не поддерживается,
какие доступы нужны и где они настроены. Отдать TL.
