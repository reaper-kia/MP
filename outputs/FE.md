# FE — фронтенд-разработчик (веб + расширение)

Зона: `frontend/**`, `extension/**`. Дизайн экранов и тексты делает дизайнер — [UI.md](UI.md); твоя
задача — **работающий** интерфейс по контракту. Пока макета нет, верстаешь на компонентах Mantine по
описанию из задачи, потом подтягиваешь стили.

**Где смотреть поля и типы:**

| Что | Файл |
|---|---|
| Все ручки, параметры, коды ответов, примеры | [`docs/API.md`](../API.md) (сгенерирован из контракта, читать удобно) |
| TypeScript-типы всех схем | [`docs/api-types.ts`](../api-types.ts) (для чтения; в код — генерация, FE-01) |
| Первоисточник (из него Prism и генерация типов) | [`contracts/http/openapi.yaml`](../../contracts/http/openapi.yaml) |
| Правила продукта (дедуп, регион, статусы) | [`docs/ARCHITECTURE.md` §5](../ARCHITECTURE.md) |

В каждой задаче ниже — ручки и типы, которые она использует, прямо в тексте. Если в задаче и в
`openapi.yaml` что-то расходится — прав `openapi.yaml`, напиши TL.

**Стек** (поверх шаблона React 19 + Vite + TS):
`react-router` · `@tanstack/react-query` · `@mantine/core` `@mantine/dates` `@mantine/notifications` ·
`dayjs` (+ `utc`, `timezone`, locale `ru`) · `openapi-typescript` + `openapi-fetch` · `msw`.

**Сквозные правила.**
- Авторизации нет: страницу логина и токены из шаблона убрать (`AuthPage`, refresh в `client.ts`).
- Все `*_at` приходят в UTC (ISO 8601) → показывать в `Asia/Krasnoyarsk`, формат `15.10.2026, 10:20`.
- Даты периода отправляются строкой `YYYY-MM-DD` — **без** перевода в UTC.
- `null` в данных = «нет данных»: показываем словами, не прячем и не подставляем 0.
- Ошибка API: `{"error": {"code","message","request_id","details"}}` — решаем по `code`
  (таблица в конце файла), `message` можно показать как есть (он по-русски).
- Массивы в query — повторением ключа: `?relevance=direct&relevance=disputed` (`openapi-fetch` с
  `querySerializer: { array: { style: "form", explode: true } }`).

---

### [ ] FE-01 · P0 · к H+2 · база, клиент, моки Prism
**Сделать.**
1. Зависимости из «Стек».
2. Типы: `npx openapi-typescript ../contracts/http/openapi.yaml -o src/api/schema.d.ts`; скрипт
   `"gen:api"` в `package.json`. Клиент `src/api/client.ts` на `openapi-fetch`:
   ```ts
   import createClient from "openapi-fetch";
   import type { paths, components } from "./schema";
   export type S = components["schemas"];            // S["Search"], S["Result"], ...
   export const api = createClient<paths>({
     baseUrl: import.meta.env.VITE_API_URL ?? "",
     querySerializer: { array: { style: "form", explode: true } },
   });
   export class ApiError extends Error {
     constructor(public status: number, public code: string, message: string,
                 public details: unknown[] = [], public requestId = "") { super(message); }
   }
   // обёртка: если !response.ok → throw new ApiError(status, error.code, error.message, ...)
   ```
3. Prism: `npx @stoplight/prism-cli@5 mock ../contracts/http/openapi.yaml -p 4010`;
   `vite.config.ts`: proxy `/api` → `process.env.VITE_API_TARGET ?? "http://localhost:4010"`.
   Скрипт `"mock": "prism mock ..."`.
4. Роуты: `/` — форма поиска; `/search/:searchId` — форма + подборка; `/sources` — источники;
   `/history` — история. Layout: шапка с навигацией «Поиск · Источники · История».
5. `dayjs.tz.setDefault("Asia/Krasnoyarsk")`, локаль `ru`; хелперы `fmtDateTime(iso)`, `fmtDate(ymd)`.

**DoD.** `npm run mock` + `npm run dev` → на `/sources` видна таблица из примера Prism; `npm run typecheck` ок.

### [ ] FE-02 · P0 · к H+4 · MSW — «живые» сценарии
Prism отвечает всегда одним примером, а поиск меняется во времени. Нужен stateful-мок.

**Сделать.** `src/mocks/{handlers.ts,db.ts,fixtures/*.ts}`, включение `VITE_MOCKS=1`
(`if (import.meta.env.VITE_MOCKS) await worker.start()` до `render`). В `db.ts` — in-memory
`searches: Map<string, S["Search"]>`, `results: Map<string, S["Result"][]>`, `sources: S["Source"][]`.

Поведение `GET /api/v1/searches/:id` — по времени с момента `POST`:

| Секунды | `status` | `stage` | `targets[].status` |
|---|---|---|---|
| 0–1 | `queued` | `queued` | все `pending` |
| 1–2 | `running` | `analyzing_query` | `pending`; появляется `query_analysis` |
| 2–8 | `running` | `collecting` | по одной цели раз в 1.5 с → `running` → `done`/`empty`/`failed` |
| 8–9 | `running` | `scoring` | — |
| 9–10 | `running` | `grouping` | — |
| 10+ | финальный (по сценарию) | `done` | — |

Сценарии по тексту запроса (`query`):

| В запросе | Итог | Что внутри |
|---|---|---|
| «безопасность» | `partial` | 4 цели (VK источник, «Поиск по всему VK», OK — `failed` `TIMEOUT`, MAX — `empty`); 25 результатов: 15 direct / 6 indirect / 4 disputed, 3 группы по 2–3 размещения, 1 с `published_at: null`, 2 с `title_source: "post_start"`; `counts.rejected: 436` |
| длинный текст (> 300 символов) | `completed` | `query_analysis.query_type: "news_text"`; 1 группа из 3 размещений (копия, сокращение, пересказ) + 1 `rejected` «другое событие» |
| «пусто» | `completed` | `counts.total: 0`, все цели `done`/`empty` |
| «ошибка» | `failed` | все цели `failed`, `PLATFORM_UNAVAILABLE` |
| иначе | `completed` | 10 результатов |

Остальные ручки: `results`/`groups` — фильтры `relevance`, `platform`, `target_id`, `date_status`,
`include_excluded`, `sort`, `limit/offset` реально применяются к массиву; `exclusion` меняет
`excluded` и пересчитывает `counts`; `retry` переводит `failed` цели в `pending` и через 3 с в `done`;
`cancel` → `cancelled`; `export` отдаёт `new Blob(["mock"])` с `Content-Disposition`; источники — CRUD
по массиву, `resolve` для URL с «exists» → `existing_source_id`, для «bad» → 422 `UNSUPPORTED_URL`.

**DoD.** Все 5 сценариев ТЗ проходятся в UI при `VITE_MOCKS=1` без бэкенда.

### [ ] FE-03 · P0 · к H+8 · форма поиска (шаги 1–3 из ТЗ)
**API.**

| Действие | Ручка | Тело / параметры | Ответ |
|---|---|---|---|
| Загрузить площадки | [`GET /api/v1/platforms`](../API.md#listplatforms) | — | `PlatformInfo[]` |
| Подсказка по запросу | [`POST /api/v1/query/analyze`](../API.md#analyzequery) | `{ query: string }` (3–20000 симв.) | `QueryAnalysis` |
| Источники для выбора | [`GET /api/v1/sources`](../API.md#listsources) | `platform[]`, `q`, `is_active`, `limit≤200`, `offset` | `SourcePage` |
| Запуск | [`POST /api/v1/searches`](../API.md#startsearch) | `SearchCreateIn` | `202 Search` |

```ts
type Platform = "vk" | "ok" | "max" | "news";
interface PlatformInfo { code: Platform; title: string; source_mode: boolean; global_mode: boolean;
  status: "ok" | "degraded" | "unavailable"; note: string | null; }
interface QueryAnalysis { query_type: "topic" | "event" | "person" | "news_text"; summary: string;
  search_queries: string[]; needs_clarification: boolean; clarification_hint: string | null; }
interface SearchCreateIn {
  query: string;                 // 3..20000, одно поле на всё
  period_from: string;           // "YYYY-MM-DD", Красноярск, включительно
  period_to: string;             // "YYYY-MM-DD", >= period_from
  mode: "selected" | "global";
  platforms: Platform[];         // минимум 1
  source_ids: string[];          // uuid; непустой при mode="selected", [] при "global"
}
```

**Поведение.**
1. Поле «Что ищем?» — `Textarea autosize minRows=2 maxRows=12`. Через 800 мс после последнего ввода
   (и если длина ≥ 3) — `analyzeQuery`; показываем под полем: «Понято как: {тип} — {summary}».
   Тип словами: `topic` «тема», `event` «событие», `person` «человек», `news_text` «текст новости —
   ищем её размещения». `needs_clarification` → жёлтая подсказка `clarification_hint`. Ошибка анализа
   → ничего не показываем (кнопку не блокируем).
2. Период: `SegmentedControl` «Сегодня / 7 дней / 30 дней / Свой» + `DatePickerInput type="range"`.
   По умолчанию «7 дней»: `period_to = сегодня(Красноярск)`, `period_from = period_to − 6 дней`.
   Подпись «по дате публикации».
3. Где искать: `SegmentedControl` «Только мои источники» (`selected`) / «Везде» (`global`).
   Чекбоксы площадок из `/platforms`: `status="unavailable"` → disabled + `Tooltip(note)`;
   в режиме `global` площадка с `global_mode=false` — чекбокс активен, но подсказка «здесь — только по
   источникам из списка».
4. Режим `selected`: чипы выбранных источников (до 8 видно, дальше «+N») + кнопка «Изменить список»
   → `Drawer`: поиск `q` (debounce 300 мс), фильтр по площадке, чекбоксы, «Выбрать все {площадка}»,
   «Снять все». По умолчанию выбраны все `is_active=true` выбранных площадок. Выбор хранить в
   `localStorage` (в try/catch).
5. Строка про регион с `ⓘ`: «Красноярский край: публикация из регионального источника или с
   упоминанием края в тексте».
6. «Найти» (и Ctrl+Enter). Клиентская валидация до запроса: длина запроса ≥ 3, даты, ≥ 1 площадка,
   при `selected` ≥ 1 источник. 422 от сервера → `details[].field` подсветить у поля, иначе — уведомление.
7. Успех → `navigate(/search/${search.id})`. Форма остаётся над подборкой со значениями
   из `search.params` (а не из локального состояния) — так видно, к чему относится подборка.

**DoD.** На Prism и MSW: валидация, оба режима, подсказка анализа, переход на `/search/:id`.

### [ ] FE-04 · P0 · к H+10 · ход поиска и «Где искали» (сценарии 3, 5)
**API.**

| Действие | Ручка | Ответ |
|---|---|---|
| Статус | [`GET /api/v1/searches/{search_id}`](../API.md#getsearch) | `Search` |
| Повторить | [`POST /api/v1/searches/{search_id}/retry`](../API.md#retrysearch) `{ target_ids?: string[] }` (пусто = все failed) | `202 Search` |
| Остановить | [`POST /api/v1/searches/{search_id}/cancel`](../API.md#cancelsearch) | `Search` |

```ts
type SearchStatus = "queued" | "running" | "completed" | "partial" | "failed" | "cancelled";
type SearchStage  = "queued" | "analyzing_query" | "collecting" | "scoring" | "grouping" | "done";
type TargetStatus = "pending" | "running" | "done" | "empty" | "failed" | "skipped";
interface ErrorInfo { code: string; message: string; }   // message — по-русски, показывать как есть
interface SearchTarget {
  id: string; kind: "source" | "platform_search"; platform: Platform;
  source_id: string | null; name: string; url: string | null;   // name — снимок на момент поиска
  status: TargetStatus; fetched: number; matched: number;        // получено / из них в подборке
  error: ErrorInfo | null; attempts: number; finished_at: string | null;
}
interface Search {
  id: string; status: SearchStatus; stage: SearchStage;
  progress: { targets_total: number; targets_finished: number; percent: number };  // percent 0..100
  params: SearchParams; query_analysis: QueryAnalysis | null;
  targets: SearchTarget[]; counts: SearchCounts; warnings: string[];
  created_at: string; started_at: string | null; finished_at: string | null;
}
```

**Поведение.**
- `useQuery(["search", id], …, { refetchInterval: s => isFinal(s?.status) ? false : 1500 })`,
  `isFinal = ["completed","partial","failed","cancelled"]`.
- Стадия словами: `queued` «В очереди…», `analyzing_query` «Разбираем запрос…», `collecting`
  «Собираем публикации — {targets_finished} из {targets_total} источников», `scoring` «Проверяем связь
  с запросом…», `grouping` «Группируем одинаковые новости…». `Progress value={percent}`.
- Блок «Где искали» (`Accordion`): раскрыт во время поиска, после финала свёрнут в строку
  «Обработано {done+empty} из {N} · не удалось: {failed}». Строка цели: иконка площадки · `name`
  (ссылка на `url`, если есть; для `platform_search` — без ссылки) · статус-бейдж · «получено
  {fetched} · в подборке {matched}» · `error.message` · кнопка «Повторить» (только `failed`,
  `retry({target_ids:[id]})`). Над списком «Повторить все неудачные» (если есть `failed` и поиск финальный).
- Клик по строке цели → фильтр результатов `target_id=[id]` (FE-05), повторный клик снимает.
- «Остановить» видно, пока не финальный.
- `warnings[]` — серые строки под прогрессом.
- 409 `SEARCH_NOT_FINISHED` на retry → уведомление «Дождитесь окончания поиска».

**DoD.** На MSW-сценарии «безопасность»: видно, как цели проходят статусы; OK падает с текстом;
«Повторить» поднимает её до `done`.

### [ ] FE-05 · P0 · к H+12 · подборка (шаг 4; сценарии 1, 2, 4)
**API.**

| Действие | Ручка | Параметры | Ответ |
|---|---|---|---|
| Список | [`GET /api/v1/searches/{id}/results`](../API.md#listresults) | `relevance[]`, `platform[]`, `target_id[]`, `date_status[]`, `include_excluded`, `sort`, `limit≤200`, `offset` | `ResultPage {items: Result[], total, has_more}` |
| По сюжетам | [`GET /api/v1/searches/{id}/groups`](../API.md#listgroups) | `relevance[]`, `platform[]`, `include_excluded`, `limit`, `offset` | `GroupPage {items: ResultGroup[], total, has_more}` |
| Исключить / вернуть | [`POST /api/v1/searches/{id}/results/exclusion`](../API.md#setexcluded) | `{ result_ids: string[] (≥1), excluded: boolean }` | `{ counts: SearchCounts }` |

```ts
type Relevance = "direct" | "indirect" | "disputed" | "rejected";
interface SearchCounts {
  total: number;      // в подборке = direct+indirect+disputed без исключённых; каждое размещение отдельно
  direct: number; indirect: number; disputed: number;
  rejected: number;   // отсеяно системой (не в total)
  excluded: number;   // исключено пользователем (не в total)
  unknown_date: number;  // из total — без даты
  groups: number;     // сюжетов среди total
}
interface ExcerptPart { text: string; highlight: boolean; }
interface Result {
  id: string; publication_id: string; platform: Platform;
  source: { id: string | null; name: string; url: string; is_regional: boolean };  // id=null — не в каталоге
  url: string;                                   // прямая ссылка на пост
  title: string; title_source: "title" | "post_start";
  excerpt: string; excerpt_parts: ExcerptPart[]; // дословный фрагмент; рендерить parts
  published_at: string | null; date_status: "in_period" | "unknown";
  relevance: Relevance; score: number; explanation: string;   // score 0..1 — НЕ показывать числом
  region: { by_source: boolean; by_content: boolean; evidence: string | null };
  sentiment: "positive" | "neutral" | "negative" | null;
  group_id: string | null; group_size: number;
  metrics: { views: number | null; likes: number | null; reposts: number | null; comments: number | null };
  excluded: boolean; found_by_target_id: string;
}
interface ResultGroup { group_id: string; title: string; size: number; platforms: Platform[];
  earliest_published_at: string | null; items: Result[]; }   // items — ВСЕ размещения
```

**Поведение.**
1. **Плашка параметров** (sticky под формой) из `search.params` и `counts.total`:
   «Подборка: «{query, обрезать до 80}» · {dd.mm}–{dd.mm.yyyy} · {Только мои источники | Везде} ·
   {VK, OK, MAX} · **{total} публикаций**». Если пользователь изменил любое поле формы после
   запуска (сравнить текущие значения формы с `search.params`) — жёлтый баннер «Параметры изменены.
   Ниже — подборка по прежним условиям» + кнопка «Найти заново».
2. **Вкладки**: «Все {total}» (`relevance` не передаём) · «Прямые {direct}» · «Косвенные {indirect}» ·
   «Спорные {disputed}»; справа ссылкой «Отсеяно системой ({rejected})» → `relevance=["rejected"]`
   (пометка над списком «Эти публикации система сочла не относящимися к запросу»).
3. Фильтры: площадка (`platform[]`), «Только без даты» (`date_status=["unknown"]`), «Показать
   исключённые ({excluded})» (`include_excluded=true`); сортировка `relevance` / `date_desc` / `date_asc`.
   Состояние фильтров — в URL search params (чтобы экспорт и «назад» работали).
4. **Карточка публикации** (компонент `ResultCard`):
   - иконка `platform` · `source.name` (ссылка `source.url`) · бейдж «Региональный источник», если
     `source.is_regional`;
   - заголовок `title`; если `title_source === "post_start"` — серая пометка «начало поста»;
   - дата: `published_at ? fmtDateTime : «Дата недоступна»` (оранжевым, с `ⓘ` «площадка не отдала
     дату — может быть вне периода»);
   - выдержка: `excerpt_parts.map(p => p.highlight ? <mark>{p.text}</mark> : p.text)`, 3 строки,
     «Показать полностью»;
   - чип связи: `direct` «Прямая связь» · `indirect` «Косвенная» · `disputed` «Спорно — проверьте» ·
     `rejected` «Отсеяно»; в `Tooltip` — `explanation`;
   - регион: `region.by_content && evidence` → бейдж «Упоминается: {evidence}»;
   - тональность: `positive` «позитивная» / `neutral` «нейтральная» / `negative` «негативная» /
     `null` — не показывать;
   - метрики: показывать только не-`null` («👁 5 400 · ♥ 31 · ↻ 4»);
   - кнопка «Открыть пост» `<a href={url} target="_blank" rel="noopener noreferrer">`;
   - чекбокс «Исключить» (и выделение для массового действия).
5. **Группировка**: `Switch` «Группировать одинаковые новости» → `/groups`. Карточка сюжета: `title` ·
   «{size} размещений» · иконки `platforms` · `earliest_published_at`; раскрытие показывает все `items`
   как `ResultCard` в компактном виде. Подпись над списком: «В счёте каждое размещение — отдельная
   публикация». Действие «Исключить весь сюжет» = `exclusion` со всеми `items[].id`.
6. **Исключение**: оптимистично убрать из списка, после ответа обновить `counts` в кэше `["search", id]`
   и инвалидировать списки. Плашка «Исключено: 3 · Вернуть».
7. Пока `status` не финальный — список перезапрашивать раз в 3 с (результаты прибывают). Пагинация
   «Показать ещё» по `has_more` (limit 50), проверить на 300 элементах.

**DoD.** На MSW-сценарии «безопасность»: вкладки с числами, группа раскрывается со всеми ссылками,
пост без даты помечен, исключение уменьшает `total`.

### [ ] FE-06 · P0 · к H+12 · состояния (сценарий 5)
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

### [ ] FE-07 · P0 · к H+12 · выгрузка (шаг 5)
**API.** [`GET /api/v1/searches/{id}/export?format=xlsx|docx`](../API.md#exportsearch) + те же
`relevance[]`, `platform[]`, `sort`, что сейчас на экране. Ответ — файл (`Content-Disposition`).

**Сделать.** Кнопка «Скачать Excel» (основная) — `<a href={url} download>`, где `url` собирается из
текущих фильтров (URL search params, FE-05). «Скачать Word» — вторичная (если B2-10 не готов — скрыть
флагом `VITE_DOCX=0`). Рядом текст «В файл попадёт {total с учётом фильтра} публикаций».
Пока поиск не финальный — кнопка disabled с подсказкой «Дождитесь окончания поиска».
Вкладка «Отсеяно» — экспорт отключён.

**DoD.** На gateway: число строк в XLSX = число на экране при тех же фильтрах.

### [ ] FE-08 · P0 · к H+16 · управление источниками
**API.**

| Действие | Ручка | Тело / параметры | Ответ / ошибки |
|---|---|---|---|
| Список | [`GET /api/v1/sources`](../API.md#listsources) | `platform[]`, `q`, `is_active`, `limit`, `offset` | `SourcePage {items: Source[], total, has_more}` |
| Предпросмотр | [`POST /api/v1/sources/resolve`](../API.md#resolvesource) | `{ url }` | `SourcePreview`; 404 `SOURCE_NOT_FOUND`, 422 `UNSUPPORTED_URL`, 503 `PLATFORM_UNAVAILABLE` |
| Добавить | [`POST /api/v1/sources`](../API.md#createsource) | `{ url, name?: string\|null, is_regional?: boolean = true, notes?: string = "" }` | `201 Source`; 409 `SOURCE_ALREADY_EXISTS` |
| Изменить | [`PATCH /api/v1/sources/{id}`](../API.md#updatesource) | любые из `{ name, is_regional, is_active, notes }` | `Source` |
| Удалить | [`DELETE /api/v1/sources/{id}`](../API.md#deletesource) | — | `204` |
| Импорт (P2) | [`POST /api/v1/sources/import`](../API.md#importsources) | `multipart/form-data`, поле `file` (.xlsx) | `{ created, duplicates, failed: {row, value, code, message}[] }` |

```ts
interface Source { id: string; platform: Platform; external_id: string; url: string; name: string;
  city: string | null; is_regional: boolean; is_active: boolean; notes: string;
  created_at: string; updated_at: string; }
interface SourcePreview { platform: Platform; external_id: string; url: string; name: string;
  city: string | null; members_count: number | null; existing_source_id: string | null; }
```

**Поведение.** Таблица: площадка · название (ссылка) · город (`null` → «—») · «Региональный»
(`Switch`, сразу PATCH) · «Активный» (`Switch`, подпись в шапке столбца: «участвует в поиске «Везде»»)
· заметка · действия. Поиск по `q` (debounce 300 мс), фильтр площадки, пагинация 50.
Добавление: поле «Ссылка на группу или канал» → по blur/Enter `resolve` → карточка (название,
площадка, город, «{members_count} подписчиков» если не `null`) → если `existing_source_id` — «Уже в
списке» + ссылка на строку, кнопка выключена; иначе «Добавить» (+ чекбокс «Региональный», по
умолчанию вкл.). Удаление — `Modal` «Удалить «{name}»? История прошлых поисков сохранится».
Ошибки — по таблице кодов ниже.

### [ ] FE-09 · P1 · к H+20 · история поисков
[`GET /api/v1/searches?limit&offset`](../API.md#listsearches) → `{ items: SearchSummary[], has_more }`,
`SearchSummary = { id, status, params: SearchParams, counts: SearchCounts, created_at, finished_at }`.
Страница `/history`: строка — запрос (обрезка 100) · период · режим · площадки · статус-бейдж ·
«{counts.total} публикаций» · `created_at` → клик `/search/:id`. «Показать ещё» по `has_more`.

### [ ] FE-10 · P1 · к H+30 · расширение Chrome (MV3)
**Сделать.** `extension/manifest.json`:
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
`VITE_API_URL=http://<IP_СЕРВЕРА>`, роутер — `createHashRouter` (в расширении нет серверных путей).
В шапке side panel кнопка «Добавить эту страницу в источники»: `chrome.tabs.query({active:true,
currentWindow:true})` → `tab.url` → тот же поток, что FE-08 (`resolve` → предпросмотр → `create`).
Показывать кнопку, только если `typeof chrome !== "undefined" && chrome.tabs`.
Скрипт `npm run build:ext`; инструкция установки — TL в README.

**DoD.** Расширение ставится через «Загрузить распакованное», side panel работает с сервером,
страница vk.com/<группа> добавляется в источники в два клика.

### [ ] FE-11 · P1 · H+20 → H+36 · перенос макетов и полировка
Перенести токены и компоненты из макетов UI-02…UI-05 (Mantine theme: цвета, шрифт, радиусы,
размеры). Сверить все состояния из UI-04. Проверить 1366×768 и 1920×1080. Переключить
`VITE_API_TARGET` на gateway и пройти 5 сценариев на стенде вместе с TL.

---

## Коды ошибок → что показать

| `code` | HTTP | Где | Текст пользователю |
|---|---|---|---|
| `VALIDATION_ERROR` / `SEARCH_INVALID_PARAMS` | 422 | формы | подсветить поле из `details[].field`, текст — `details[].message` или `message` |
| `UNSUPPORTED_URL` | 422 | источники | «Это не похоже на ссылку на группу VK, OK или канал MAX» |
| `SOURCE_NOT_FOUND` | 404 | источники | «Такой группы или канала не нашлось — проверьте ссылку» |
| `SOURCE_PRIVATE` | 409 | источники | «Группа закрыта — публикации недоступны» |
| `SOURCE_ALREADY_EXISTS` | 409 | источники | «Этот источник уже есть в списке» |
| `PLATFORM_UNAVAILABLE` | 503 | везде | «{Площадка} сейчас недоступна, попробуйте позже» |
| `RATE_LIMITED` | 429 | везде | «Слишком много запросов к площадке, подождите минуту» |
| `SEARCH_NOT_FOUND` | 404 | `/search/:id` | экран «Поиск не найден» + «Новый поиск» |
| `SEARCH_NOT_FINISHED` | 409 | retry | «Дождитесь окончания поиска» |
| `RESULT_NOT_FOUND` | 404 | исключение | обновить список молча |
| `SERVICE_UNAVAILABLE` / `UPSTREAM_ERROR` | 503 / 502 | везде | «Сервис временно недоступен. Повторить» |

Коды ошибок **источников внутри поиска** (`targets[].error.code`): `PLATFORM_UNAVAILABLE`,
`SOURCE_NOT_FOUND`, `SOURCE_PRIVATE`, `RATE_LIMITED`, `TIMEOUT`, `PARSE_ERROR`, `AUTH_REQUIRED` —
показываем `error.message` как есть (бэкенд пишет его по-русски).
