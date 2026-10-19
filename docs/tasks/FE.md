# FE — фронтенд-разработчик (веб + расширение)

Зона: `frontend/**`, `extension/**`. Дизайн экранов и тексты делает дизайнер — [UI.md](UI.md); твоя
задача — **работающий** интерфейс по контракту. Пока макета нет, верстаешь на компонентах Mantine по
описанию из задачи, потом подтягиваешь стили (FE-11).

**Где смотреть поля и типы:**

| Что | Файл |
|---|---|
| Все ручки, параметры, коды ответов, примеры | [`docs/API.md`](../API.md) (сгенерирован из контракта) |
| TypeScript-типы в коде | `src/api/schema.d.ts` (`npm run gen:api` из `openapi.yaml`); для чтения — [`docs/api-types.ts`](../api-types.ts) |
| Первоисточник (из него Prism и генерация типов) | [`contracts/http/openapi.yaml`](../../contracts/http/openapi.yaml) |
| Правила продукта (дедуп, регион, статусы) | [`docs/ARCHITECTURE.md` §5](../ARCHITECTURE.md) |

Если в задаче и в `openapi.yaml` что-то расходится — прав `openapi.yaml`, напиши TL.

**Стек (стоит):** Vite 7 · React 19 · TypeScript · `react-router` · `@tanstack/react-query` ·
`@mantine/core` `@mantine/dates` `@mantine/notifications` · `dayjs` (`utc`, `timezone`, `ru`) ·
`openapi-typescript` + `openapi-fetch` · `msw` · Prism (`@stoplight/prism-cli`).

## Старт после pull

```bash
cd frontend
npm install
npm run typecheck && npm run build      # CI делает только build — typecheck запускай сам
npm run dev:mocks                       # http://127.0.0.1:5173 — MSW в браузере, бэкенд не нужен
```

Сценарии MSW — по словам в запросе: «безопасность» (частичный итог, OK падает с `TIMEOUT`, 3 группы,
пост без даты), «пусто», «ошибка», «сбой» (с 4-й по 12-ю секунду сервер «пропадает» — уведомление «Нет связи
с сервером»), текст длиннее 300 символов (поиск по тексту новости), иначе — 10 результатов. Ссылка с «bad» →
422 `UNSUPPORTED_URL`, «notfound» → 404, «private» → 409 `SOURCE_PRIVATE`, «down» → 503, «exists» → «уже в списке».

На живом gateway (стенд — вариант Б из [README](../../README.md#быстрый-старт-после-pull)):

```bash
VITE_API_TARGET=http://127.0.0.1:8000 npm run dev        # PowerShell: $env:VITE_API_TARGET="http://127.0.0.1:8000"; npm run dev
```

Проверка: после `make smoke` в «Источниках» есть источник VK; поиск «Безопасность дорожного движения» в
режиме «Только мои источники» доходит до подборки с постами `[FAKE]`. На Windows — только `127.0.0.1`.

**Ветка `fe-p0`.** FE-06, FE-07, FE-08, FE-09 и правки FE-12 — в ветке `fe-p0` (от `main`), ждут PR.
Старая WIP-ветка FE-06 не нашлась — FE-06 написан заново по этому описанию.

**Сквозные правила.**
- Авторизации нет.
- Все `*_at` приходят в UTC (ISO 8601) → показывать в `Asia/Krasnoyarsk`, формат `15.10.2026, 10:20`
  (`src/lib/dates.ts`).
- Даты периода отправляются строкой `YYYY-MM-DD` — **без** перевода в UTC.
- `null` в данных = «нет данных»: показываем словами, не прячем и не подставляем 0.
- Ошибка API: `{"error": {"code","message","request_id","details"}}` — решаем по `code` (таблица в конце
  файла, код — `src/lib/errors.ts`), `message` можно показать как есть (он по-русски).
- Массивы в query — повторением ключа (`querySerializer` в `src/api/client.ts` уже настроен).

---

### [x] FE-01 · P0 · к H+2 · база, клиент, моки Prism
> Сделано: `src/api/client.ts` (openapi-fetch, `ApiError`, `unwrap`), типы `src/api/schema.d.ts` (`npm run
> gen:api`), Prism (`npm run mock`, :4010), прокси `/api` → `VITE_API_TARGET` (по умолчанию
> `http://127.0.0.1:4010`), роуты `/`, `/search/:searchId`, `/sources`, `/history`, шапка с навигацией,
> `dayjs` в Красноярске.

### [x] FE-02 · P0 · к H+4 · MSW — «живые» сценарии
> Сделано: `src/mocks/{handlers.ts,db.ts,fixtures/*}`, режим `npm run dev:mocks` (`VITE_MOCKS=1`); поиск
> меняется во времени по таблице стадий, 5 сценариев по тексту запроса, фильтры / исключение / retry /
> cancel / export / CRUD источников реально работают на массивах.

### [x] FE-03 · P0 · к H+8 · форма поиска (шаги 1–3 из ТЗ)
> Сделано: `features/search/SearchForm.tsx` — поле с разбором запроса через 800 мс («Понято как: …»,
> подсказка уточнения), период с пресетами, режим, площадки из `/platforms` (недоступные — disabled с
> подсказкой), выбор источников в Drawer (`SourcePicker.tsx`, выбор в `localStorage`), клиентская
> валидация, 422 → подсветка поля по `details[].field`, Ctrl+Enter, переход на `/search/:id`, форма
> заполняется из `search.params`.

### [x] FE-04 · P0 · к H+10 · ход поиска и «Где искали» (сценарии 3, 5)
> Сделано: `features/search/SearchProgress.tsx`, `TargetsPanel.tsx`, `useSearch.ts` — опрос раз в 1,5 с до
> финального статуса, стадии словами, прогресс, «Остановить», `warnings[]`, список целей со статусами,
> «получено / в подборке», ошибкой и «Повторить» (по одной и «все неудачные»), клик по цели → фильтр
> `target_id`, 409 `SEARCH_NOT_FINISHED` → уведомление.

### [x] FE-05 · P0 · к H+12 · подборка (шаг 4; сценарии 1, 2, 4)
> Сделано: `features/results/` — плашка параметров и баннер «Параметры изменены» (`ParamsBar.tsx`),
> вкладки с числами и «Отсеяно системой», фильтры и сортировка в URL (`filters.ts`), `ResultCard`
> (источник, «начало поста», «Дата недоступна ⓘ», выдержка с подсветкой, чип связи с объяснением, регион,
> тональность, метрики, «Открыть пост», «Исключить»), группы (`GroupCard`, «Исключить весь сюжет»),
> оптимистичное исключение с «Вернуть», опрос раз в 3 с, пока поиск идёт, «Показать ещё».
> Проверено на MSW; на живом gateway — нет (FE-12).

### [x] FE-06 · P0 · к H+12 · состояния (сценарий 5)
> Сделано: `features/search/viewState.ts` (одна функция; исключённые вручную считаются найденными, чтобы
> «исключил всё» не выглядело как «не найдено»), `SearchOutcome.tsx` — жёлтый баннер partial со списком
> неудачных и «Повторить», красный «Поиск не выполнен: причина» + «Повторить», серый «Поиск остановлен» +
> «Запустить заново», экран «Подходящие публикации не найдены» (где искали, советы, ссылка на отсеянные);
> скелетон списка, пока идёт поиск; `lib/useConnectionNotice.tsx` — «Нет связи с сервером» без очистки
> экрана, само убирается при восстановлении. Цвета статусов — `STATUS_COLOR` / `SEARCH_STATUS` в `status.ts`.
> Проверено: MSW «безопасность», «пусто», «ошибка», «сбой», «Остановить»; на gateway — `failed` (selected и
> «везде» при `COLLECTOR_FAKE=false`), «не найдено» с отсеянными при `COLLECTOR_FAKE=true`.
Логика выбора экрана — **одна функция**, чтобы не разъехалось:

```ts
function viewState(s: Search, total: number) {
  if (!isFinal(s.status)) return total > 0 ? "running_with_results" : "running";
  if (s.status === "failed")    return total > 0 ? "failed_with_results" : "failed";
  if (s.status === "cancelled") return "cancelled";
  if (total === 0) return "empty";                       // completed или partial без результатов
  return s.status === "partial" ? "partial" : "ok";
}
```

| viewState | Что показать |
|---|---|
| `running` | скелетон списка + прогресс (FE-04) |
| `empty` | «Подходящие публикации не найдены» + «Искали: {N} источников ({площадки}), {период}» + советы: «Расширьте период», «Попробуйте режим «Везде»», «Переформулируйте запрос»; если `partial` — ещё баннер про неудачные источники |
| `partial` | подборка + жёлтый баннер «Не удалось обработать {failed} источника(ов)» + «Повторить» |
| `failed` / `failed_with_results` | красный блок «Поиск не выполнен: {targets[].error.message первой}» + «Повторить»; найденное (если есть) остаётся ниже |
| `cancelled` | серый баннер «Поиск остановлен» + что успели найти |
| ошибка сети / 5xx | `notifications.show` красное «Нет связи с сервером. Повторить» — данные на экране не стираем |

Цвета статусов — одни и те же во всём приложении (токены от дизайнера, UI-02).
На живом стенде `failed` получается легко: `COLLECTOR_FAKE=false` без ключа VK — у каждой цели текст
«ВКонтакте: не настроен доступ (VK_SERVICE_TOKEN)»; поиск «везде» по OK / MAX — «не реализован».

**DoD.** Все строки таблицы видны на MSW («пусто», «ошибка», «безопасность») и `failed` — на gateway.

### [x] FE-07 · P0 · к H+12 · выгрузка (шаг 5)
> Сделано: `features/results/ExportBar.tsx` — «Скачать Excel», «Скачать Word» под `VITE_DOCX=1`,
> «В файл попадёт N» (total той же выборки без исключённых), disabled-подсказки. Параметры — `exportQuery()` в
> `filters.ts` (в режиме сюжетов — только relevance и platform, как на экране). Скачивание через `fetch → blob`,
> а не голым переходом: так 501 / 404 показываются уведомлением, а не скачиваются JSON-файлом; `href` у кнопки
> остаётся. Проверено на gateway: строк со ссылками в XLSX = числу на экране — все (8), после исключения (7),
> только VK (1), сюжеты (7).
**API.** [`GET /api/v1/searches/{id}/export?format=xlsx|docx`](../API.md#exportsearch) + те же
`relevance[]`, `platform[]`, `sort`, что сейчас на экране. Ответ — файл (`Content-Disposition`).
Бэкенд: XLSX работает (строк со ссылками = `counts.total`, проверено smoke); DOCX → 501 `NOT_IMPLEMENTED`
до B2-10.

**Сделать.** Кнопка «Скачать Excel» (основная) — `<a href={url} download>`, где `url` собирается из
текущих фильтров (параметры уже собирает `features/results/filters.ts` для `/results`). «Скачать Word» —
вторичная, **скрыта**, пока B2-10 не готов (флаг `VITE_DOCX`, по умолчанию выключен; добавить в
`vite-env.d.ts`). Рядом текст «В файл попадёт {total с учётом фильтра} публикаций». Пока поиск не
финальный — кнопка disabled с подсказкой «Дождитесь окончания поиска». Вкладка «Отсеяно» — экспорт отключён.

**DoD.** На gateway: число строк в XLSX = число на экране при тех же фильтрах.

### [x] FE-08 · P0 · к H+16 · управление источниками
> Сделано: `pages/SourcesPage.tsx`, `features/sources/{useSources.ts, AddSource.tsx}` — всё из «Поведения»
> ниже; заметка правится по клику; «Уже в списке» → «Показать в таблице» (фильтр + подсветка строки);
> после добавления фильтры сбрасываются, новая строка подсвечена. Импорт спрятан (P2, ждёт B2-10).
> `AddSource` принимает `initialUrl` — для кнопки в расширении (FE-10).
> Проверено на gateway (`COLLECTOR_FAKE=true`): добавить → «Уже в списке» → «Активный» (PATCH, после
> перезагрузки сохранился) → заметка → удалить. При `false`: VK → «ВКонтакте: не настроен доступ…», OK / MAX → 501.

**API.**

| Действие | Ручка | Тело / параметры | Ответ / ошибки |
|---|---|---|---|
| Список | [`GET /api/v1/sources`](../API.md#listsources) | `platform[]`, `q`, `is_active`, `limit`, `offset` | `SourcePage {items: Source[], total, has_more}` |
| Предпросмотр | [`POST /api/v1/sources/resolve`](../API.md#resolvesource) | `{ url }` | `SourcePreview`; 404 `SOURCE_NOT_FOUND`, 422 `UNSUPPORTED_URL`, 503 `PLATFORM_UNAVAILABLE`, 501 для OK / MAX (пока) |
| Добавить | [`POST /api/v1/sources`](../API.md#createsource) | `{ url, name?: string\|null, is_regional?: boolean = true, notes?: string = "" }` | `201 Source`; 409 `SOURCE_ALREADY_EXISTS` |
| Изменить | [`PATCH /api/v1/sources/{id}`](../API.md#updatesource) | любые из `{ name, is_regional, is_active, notes }` | `Source` |
| Удалить | [`DELETE /api/v1/sources/{id}`](../API.md#deletesource) | — | `204` |
| Импорт (P2) | [`POST /api/v1/sources/import`](../API.md#importsources) | `multipart/form-data`, поле `file` (.xlsx) | `{ created, duplicates, failed: {row, value, code, message}[] }`; сейчас 501 |

**Поведение.** Таблица: площадка · название (ссылка) · город (`null` → «—») · «Региональный»
(`Switch`, сразу PATCH) · «Активный» (`Switch`, подпись в шапке столбца: «участвует в поиске «Везде»»)
· заметка · действия. Поиск по `q` (debounce 300 мс), фильтр площадки, пагинация 50.
Добавление: поле «Ссылка на группу или канал» → по blur / Enter `resolve` → карточка (название,
площадка, город, «{members_count} подписчиков» если не `null`) → если `existing_source_id` — «Уже в
списке» + ссылка на строку, кнопка выключена; иначе «Добавить» (+ чекбокс «Региональный», по
умолчанию вкл.). Удаление — `Modal` «Удалить «{name}»? История прошлых поисков сохранится».
Ошибки — по таблице кодов ниже. Импорт — спрятать, пока B2-10 не готов.

### [x] FE-12 · P0 · к H+14 · прогон на живом gateway
> Сделано: стенд без Docker (Postgres 16 на 5435, 4 сервиса, gateway), `make smoke` → `All good`; фронт через
> `VITE_API_TARGET`. Сценарии 1 (по источникам и «везде»), 3 (баннер «Параметры изменены», видно, где искали),
> 4 (исключение, XLSX = экран), 5 (не найдено, `failed` с текстом сервера, «Повторить» → attempts 2) — без
> «Сервис временно недоступен». `COLLECTOR_FAKE=false`: площадки disabled + подсказка в форме, цели `failed`
> с текстом сервера. п. 3 — коды в `errors.ts` и в таблице ниже; п. 4 — warning «ML работал в упрощённом
> режиме» читается. **Найденный баг фронта** (исправлен): после финала поиска список оставался пустым
> («Все 8», а карточек нет) — опрос `/results` останавливался раньше, чем бэкенд дописывал подборку.
> Не проверено на gateway: `partial` (часть целей упала, часть — нет), посты без даты, `cancelled` (фейковый
> поиск заканчивается за 2 с) — эти состояния проверены только на MSW.
**Цель.** FE-03…FE-05 проверены только на MSW и Prism. Настоящий бэкенд отвечает иначе — это надо увидеть
до демо, а не на нём.

**Сделать.**
1. Стенд без Docker (README, вариант Б) + `VITE_API_TARGET=http://127.0.0.1:8000 npm run dev`; пройти
   сценарии 1, 3, 4, 5 по `docs/demo/checklist.md` на `COLLECTOR_FAKE=true`.
2. То же с `COLLECTOR_FAKE=false` без ключа VK: площадки `unavailable`, цели `failed` с текстом сервера,
   поиск «везде» по OK / MAX.
3. Ошибки, которые на моках не встречались: `src/lib/errors.ts` показывает для **любого** 5xx без своей
   строки «Сервис временно недоступен» — поэтому 503 `PLATFORM_UNAVAILABLE` («ВКонтакте: не настроен
   доступ…») и 501 `NOT_IMPLEMENTED` («Одноклассники: resolve не реализован (B1-04)») сейчас выглядят как
   падение сервиса. Добавить оба кода в таблицу ниже и в `errors.ts` (тексты — с дизайнером, UI-04).
4. Предупреждения настоящего бэкенда («ML работал в упрощённом режиме», «Коллектор в режиме имитации»)
   — в `warnings[]`, убедиться, что читаются.
5. Найденное у бэкенда — в чат с ID задачи владельца (B2-…, B1-…).

**DoD.** Сценарии 1, 3, 4, 5 на gateway проходят без «Сервис временно недоступен» там, где сервис жив.

### [x] FE-09 · P1 · к H+20 · история поисков
> Сделано: `pages/HistoryPage.tsx`; пока поиск в списке идёт — обновление раз в 5 с. Проверено на MSW и на
> gateway (клик по строке → `/search/:id`).
[`GET /api/v1/searches?limit&offset`](../API.md#listsearches) → `{ items: SearchSummary[], has_more }`,
`SearchSummary = { id, status, params: SearchParams, counts: SearchCounts, created_at, finished_at }`.
Страница `/history`: строка — запрос (обрезка 100) · период · режим · площадки · статус-бейдж ·
«{counts.total} публикаций» · `created_at` → клик `/search/:id`. «Показать ещё» по `has_more`.

### [ ] FE-10 · P1 · к H+30 · расширение Chrome (MV3)
Папки `extension/` ещё нет. **Сделать.** `extension/manifest.json`:
```json
{ "manifest_version": 3, "name": "Медиамониторинг", "version": "1.0.0",
  "action": { "default_title": "Медиамониторинг" },
  "side_panel": { "default_path": "index.html" },
  "background": { "service_worker": "background.js" },
  "permissions": ["sidePanel", "activeTab", "tabs"],
  "host_permissions": ["http://<IP_СЕРВЕРА>/*"] }
```
`background.js`: `chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })`.
Сборка: `vite build --mode extension --outDir ../extension/dist` с `base: "./"`,
`VITE_API_URL=http://<IP_СЕРВЕРА>` (уже читается в `client.ts`), роутер — `createHashRouter` (в
расширении нет серверных путей). CORS для `chrome-extension://*` в gateway уже есть. В шапке side panel
кнопка «Добавить эту страницу в источники»: `chrome.tabs.query({active:true, currentWindow:true})` →
`tab.url` → тот же поток, что FE-08 (`resolve` → предпросмотр → `create`). Показывать кнопку, только если
`typeof chrome !== "undefined" && chrome.tabs`. Скрипт `npm run build:ext`; инструкция установки — TL в README.

**DoD.** Расширение ставится через «Загрузить распакованное», side panel работает с сервером,
страница vk.com/<группа> добавляется в источники в два клика.

### [ ] FE-11 · P1 · H+20 → H+36 · перенос макетов и полировка
Перенести токены и компоненты из макетов UI-02…UI-05 в `src/theme.ts` (сейчас там только `primaryColor`
и системный шрифт). Сверить все состояния из UI-04. Проверить 1366×768 и 1920×1080. Пройти 5 сценариев на
стенде (Docker / сервер) вместе с TL.

---

## Коды ошибок → что показать

| `code` | HTTP | Где | Текст пользователю |
|---|---|---|---|
| `VALIDATION_ERROR` / `SEARCH_INVALID_PARAMS` | 422 | формы | подсветить поле из `details[].field`, текст — `details[].message` или `message` |
| `UNSUPPORTED_URL` | 422 | источники | «Это не похоже на ссылку на группу VK, OK или канал MAX» |
| `SOURCE_NOT_FOUND` | 404 | источники | «Такой группы или канала не нашлось — проверьте ссылку» |
| `SOURCE_PRIVATE` | 409 | источники | «Группа закрыта — публикации недоступны» |
| `SOURCE_ALREADY_EXISTS` | 409 | источники | «Этот источник уже есть в списке» |
| `PLATFORM_UNAVAILABLE` | 503 | везде | `message` сервера как есть («ВКонтакте: не настроен доступ (VK_SERVICE_TOKEN)»); без него — «Площадка сейчас недоступна, попробуйте позже» |
| `NOT_IMPLEMENTED` | 501 | источники, выгрузка, импорт | временно, до UI-04: источники — «Эта площадка пока не подключена — сейчас можно добавлять только группы ВКонтакте»; выгрузка — «Выгрузка в этом формате пока недоступна»; импорт — «Загрузка списка из Excel пока недоступна» |
| `RATE_LIMITED` | 429 | везде | «Слишком много запросов к площадке, подождите минуту» |
| `SEARCH_NOT_FOUND` | 404 | `/search/:id` | экран «Поиск не найден» + «Новый поиск» |
| `SEARCH_NOT_FINISHED` | 409 | retry | «Дождитесь окончания поиска» |
| `RESULT_NOT_FOUND` | 404 | исключение | обновить список молча |
| `SERVICE_UNAVAILABLE` / `UPSTREAM_ERROR` | 503 / 502 | везде | «Сервис временно недоступен. Повторить» |

Коды ошибок **источников внутри поиска** (`targets[].error.code`): `PLATFORM_UNAVAILABLE`,
`SOURCE_NOT_FOUND`, `SOURCE_PRIVATE`, `RATE_LIMITED`, `TIMEOUT`, `PARSE_ERROR`, `AUTH_REQUIRED`, а пока OK /
MAX не подключены — и `NOT_IMPLEMENTED` — показываем `error.message` как есть (бэкенд пишет его по-русски).

## Интеграция: от кого ты зависишь

| Что | От кого |
|---|---|
| Макеты, токены, тексты состояний | UI-01…UI-05 |
| DOCX и импорт источников | B2-10 (до него — скрыть) |
| Настоящие посты на экране | B1-03 (ключ VK) |
| Docker-стенд и сервер для FE-10 / FE-11 | TL-11, TL-07 |
