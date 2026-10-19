# ML — ml_service («анализ»)

Зона: `services/ml_service/**`, `eval/**`. Контракт: `contracts/ml/v1/ml_service.proto` (gRPC).
Своей БД нет. Каркас и транспорт готовы (TL-01), ML-01 (стаб на эвристиках) уже работает —
**твоя часть — логика в `core/` и провайдеры в `providers/`**, чистые функции, которые
можно гонять из скрипта и тестов без gRPC.

```
ml_service/
  core/
    query.py        ← analyze_query(text) -> QueryAnalysis
    scoring.py      ← score_posts(query, analysis, posts) -> list[PostScore]
    same_news.py    ← режим «текст новости»: та же новость / другое событие
    grouping.py     ← group_posts(posts) -> list[PostGroup]
    region.py       ← справочник края + поиск привязки в тексте
    excerpt.py      ← лучший фрагмент + подсветка (позиции в исходном тексте)
  providers/
    llm.py          ← Protocol LLM: complete_json(prompt, schema) ; YandexGPT | Ollama | Stub
    embeddings.py   ← Protocol Embedder: embed(texts, kind=query|doc) ; Yandex | Ollama(bge-m3) | Stub
  transport/grpc/   ← servicer: proto ⇄ core
eval/
  datasets/*.jsonl  ← размеченные примеры
  run_eval.py       ← precision / recall / F1 / время
```

**Где смотреть поля и типы:** [`docs/GRPC.md` → `ml.v1`](../GRPC.md#mlv1mlservice) (все сообщения
и enum'ы с типами и комментариями), первоисточник — `contracts/ml/v1/ml_service.proto`. Нужные поля
выписаны в задачах ниже. Внутри `core/` работай со своими dataclass'ами (ниже), proto ⇄ dataclass —
только в `transport/grpc/mappers.py`: так `core` можно гонять из `eval/` без gRPC.

```python
# core/models.py — зеркало контракта
QueryType = Literal["topic", "event", "person", "news_text"]
Relevance = Literal["direct", "indirect", "disputed", "irrelevant"]
Sentiment = Literal["positive", "neutral", "negative"] | None
EntityType = Literal["person", "organization", "location", "event", "date", "number"]

@dataclass
class Entity: text: str; type: EntityType

@dataclass
class QueryAnalysis:
    query_type: QueryType
    summary: str                    # одна фраза для пользователя
    search_queries: list[str]       # 3–8 фраз для поиска по площадкам
    entities: list[Entity]
    must_concepts: list[str]
    exclude_concepts: list[str]
    needs_clarification: bool
    clarification_hint: str         # "" если не нужно

@dataclass
class Post:                         # PostForScoring
    id: str; title: str | None; text: str; source_name: str; source_is_regional: bool

@dataclass
class Span: start: int; end: int    # индексы Python-строки post.text, end не включается

@dataclass
class PostScore:
    id: str
    relevance: Relevance
    score: float                    # 0..1
    explanation: str                # 1 предложение, только по тексту поста
    region_by_content: bool
    region_evidence: str            # "" если нет
    sentiment: Sentiment
    excerpt_span: Span              # ≤ 300 символов, внутри text
    highlight_spans: list[Span]
```

Провайдер — из env: `LLM_PROVIDER=yandex|ollama|stub`, `EMBED_PROVIDER=…`. До ключей Яндекса
работаешь на Ollama (`docker compose --profile llm-local up`, модели `qwen2.5:7b-instruct`, `bge-m3`).
Организаторы рекомендуют продукты Яндекса — на демо **YandexGPT + эмбеддинги Яндекса** (имена моделей
и SDK проверить в документации Yandex AI Studio: `yandex-cloud-ml-sdk`, модели `yandexgpt-lite` /
`yandexgpt`, эмбеддинги `text-search-query` / `text-search-doc`).

**Главные правила.**
1. Ты **не пишешь** тексты постов, заголовки и ссылки. Только оценки, объяснения и позиции фрагментов.
2. Важнее **не пропустить** нужное (recall), но мусор тоже штрафуется. Сомневаешься → `DISPUTED`, а не
   `IRRELEVANT`: человек проверит.
3. Любой ответ LLM — строгий JSON → валидировать pydantic → один ретрай → фолбэк на эвристику с
   `degraded=true`. Сервис **никогда** не падает из-за кривого ответа модели.

---

### [x] ML-01 · P0 · к H+3 · стаб по контракту
> Сделано в каркасе: эвристики в `core/` (`query.py`, `scoring.py`, `grouping.py`, `region.py`,
> `excerpt.py`), `engine.py` следит за инвариантами, все ответы `degraded=true`. Дальше — ML-02…
Все 3 RPC отвечают по контракту на эвристиках: `AnalyzeQuery` — тип по длине (> 300 символов или
> 2 предложений → NEWS_TEXT, иначе TOPIC), `search_queries=[query]`; `ScorePosts` — доля общих лемм
запроса и поста → класс по порогам; `GroupPosts` — каждый пост сам по себе. Провайдеры `Stub`.
Так B2 интегрируется сразу.

**Контракт** — `service MlService` (порт 50055):

| RPC | Запрос | Ответ | Лимиты |
|---|---|---|---|
| `AnalyzeQuery` | `{context, query: str}` (3–20000 симв.) | `{analysis: QueryAnalysis, degraded: bool}` | ответ ≤ 20 с |
| `ScorePosts` | `{context, query: str, analysis: QueryAnalysis, posts: PostForScoring[]}` | `{scores: PostScore[], degraded: bool}` | ≤ 50 постов, ответ ≤ 60 с |
| `GroupPosts` | `{context, posts: PostForGrouping[]}` (`{id, optional title, text}`) | `{groups: PostGroup[]}` (`{group_id, post_ids[], representative_post_id}`) | до 500 постов |

Enum'ы proto: `QUERY_TYPE_TOPIC|EVENT|PERSON|NEWS_TEXT`, `RELEVANCE_DIRECT|INDIRECT|DISPUTED|IRRELEVANT`,
`SENTIMENT_POSITIVE|NEUTRAL|NEGATIVE` (`SENTIMENT_UNSPECIFIED` = «не определено»),
`ENTITY_TYPE_PERSON|ORGANIZATION|LOCATION|EVENT|DATE|NUMBER`. Ошибка — только если совсем не можем:
`ML_UNAVAILABLE` → `UNAVAILABLE`; в остальных случаях отвечаем эвристикой с `degraded=true`.

Python-маппинг (пример для `PostScore`):
```python
from ml.v1 import ml_service_pb2 as pb
REL = {"direct": pb.RELEVANCE_DIRECT, "indirect": pb.RELEVANCE_INDIRECT,
       "disputed": pb.RELEVANCE_DISPUTED, "irrelevant": pb.RELEVANCE_IRRELEVANT}
def score_to_proto(s: PostScore) -> pb.PostScore:
    return pb.PostScore(
        id=s.id, relevance=REL[s.relevance], score=s.score, explanation=s.explanation,
        region=pb.RegionMatch(by_content=s.region_by_content, evidence=s.region_evidence),
        sentiment=SENT.get(s.sentiment, pb.SENTIMENT_UNSPECIFIED),
        excerpt_span=pb.TextSpan(start=s.excerpt_span.start, end=s.excerpt_span.end),
        highlight_spans=[pb.TextSpan(start=h.start, end=h.end) for h in s.highlight_spans])
```

**DoD.** `grpcurl … ScorePosts` возвращает ответ на каждый пост в том же порядке.

### [ ] ML-02 · P0 · H+2 → H+12, дальше пополнять · eval-набор
**Цель.** Без замера нельзя ни настроить пороги, ни показать качество на презентации (там прямо
спрашивают «найденные, пропуски, лишние, время»).

**Сделать.** `eval/datasets/<сценарий>.jsonl`, одна строка — один пост:
```json
{"query": "Безопасность дорожного движения в Красноярском крае", "post_id": "vk:-123_456",
 "post_url": "https://vk.com/wall-123_456", "source_name": "Новости Красноярска", "source_is_regional": true,
 "title": null, "post_text": "…полный текст…", "label": "direct", "note": "рейд ГИБДД"}
```
`label`: `direct | indirect | irrelevant` (`disputed` в разметке не ставим — это ответ системы, при
подсчёте `disputed` считать «найдено», но отдельно показывать долю). Минимум:
- «Безопасность дорожного движения в Красноярском крае» — 40+ постов, **обязательно ловушки**:
  пожарная безопасность, безопасность на воде, кибербезопасность, ДТП в другом регионе;
- событие с уточнением (например, конкретное мероприятие края) и человек (глава региона/города) — по 25+;
- **сценарий 2:** исходная новость + сокращённая версия + пересказ с другим заголовком + 2–3 похожие
  новости о **другом** событии (тот же тип события, другая дата/место/участники).
Посты брать реальные (VK-поиск, публичные группы края) с URL — это же пригодится для демо.
`run_eval.py`: прогоняет `core` и печатает таблицу precision/recall/F1 по классам + среднее время на пост.
Формулы для слайда: «найдено» = predicted ∈ {direct, indirect, disputed}; recall = найдено ∩
label∈{direct,indirect} / label∈{direct,indirect}; precision = найдено ∩ label∈{direct,indirect} /
найдено; отдельно — сколько ушло в `disputed` (это работа для человека). Вывод — markdown-таблица в
`eval/report.md` (её возьмёт дизайнер в презентацию).

**DoD.** `uv run python eval/run_eval.py` печатает таблицу; набор в git.

### [ ] ML-03 · P0 · к H+10 · AnalyzeQuery v1
**Контракт:** вход `query: str`; выход `QueryAnalysis` (поля — в dataclass выше) + `degraded`.
Пример ожидаемого ответа на «Безопасность дорожного движения в Красноярском крае»:
```json
{"query_type": "topic", "summary": "Тема: безопасность дорожного движения (ДТП, ГИБДД, пешеходы) в Красноярском крае",
 "search_queries": ["безопасность дорожного движения", "ДТП Красноярск", "Госавтоинспекция Красноярский край",
                    "пешеходный переход", "рейд ГИБДД"],
 "entities": [{"text": "Красноярский край", "type": "location"}],
 "must_concepts": ["дорожное движение"], "exclude_concepts": ["пожарная безопасность", "безопасность на воде"],
 "needs_clarification": false, "clarification_hint": ""}
```
Тип запроса (правило для NEWS_TEXT + LLM для TOPIC/EVENT/PERSON). `search_queries` 3–8 коротких фраз —
**это напрямую влияет на полноту**: поиск VK лексический, нужны синонимы и формы («ДТП», «авария»,
«Госавтоинспекция», «ГИБДД», «пешеходный переход»). Для NEWS_TEXT — фразы из ключевых сущностей и
2–3 характерных словосочетаний новости + её заголовок. `must_concepts`, `exclude_concepts`,
`entities`. `needs_clarification` — если запрос из 1 общего слова («безопасность»): подсказка
«Уточните тему: дорожная, пожарная, информационная…». `summary` — одна фраза для пользователя.

**DoD.** На 10 разных запросах фразы осмысленные, тип верный ≥ 9/10.

### [ ] ML-04 · P0 · к H+12 · ScorePosts v1 (быстрый, без LLM)
**Контракт:** вход `query`, `analysis: QueryAnalysis`, `posts: Post[]` (≤ 50); выход `PostScore[]` —
**ровно по одному на пост, в том же порядке, с тем же `id`**. `excerpt_span`/`highlight_spans` — позиции в
`post.text` (не в title), `0 ≤ start < end ≤ len(text)`, выдержка ≤ 300. `explanation` — по-русски, одно
предложение, ≤ 150 символов. Тест на инварианты (длина, порядок, границы span) — обязателен.

Эмбеддинги запроса (summary + must_concepts) и постов → косинус; + пересечение лемм (`pymorphy3`) с
must/exclude-концептами → класс по порогам (пороги — по eval). Регион: `region.py` — справочник
городов/районов края (Красноярск, Норильск, Ачинск, Канск, Минусинск, Железногорск, Зеленогорск,
Лесосибирск, Назарово, Шарыпово, Дивногорск, Сосновоборск, Боготол, Бородино, Енисейск, Уяр,
Игарка, Дудинка, районы края, «Красноярский край», «Таймыр», «Эвенкия»…) с формами слов →
`by_content` + `evidence`. Выдержка: окно из 1–3 предложений с максимальной близостью к запросу →
`excerpt_span` (≤ 300 символов); подсветка — позиции совпавших лемм/сущностей.

**DoD.** eval: recall класса direct ≥ 0.8 на «БДД»; пожарная безопасность не `DIRECT`.

### [ ] ML-05 · P0 · к H+22 · ScorePosts v2 (LLM-судья)
Два этапа: эмбеддинги отсекают **явно** нерелевантное (низкий порог — экономим деньги, не теряем
полноту), остальное — LLM пачками по 5–10 постов в одном промпте → `relevance`, `explanation`
(1 предложение, только по тексту поста: «Пост о рейде ГИБДД у школ Ачинска»), `sentiment`.
Кэш по `(hash(query), hash(text))` в памяти. Таймаут → фолбэк на v1, `degraded=true`.
Записать: сколько постов уходит в LLM, сколько токенов, сколько стоит на 1000 постов.

**DoD.** eval: F1 по direct выше, чем у v1; каждое объяснение не противоречит тексту (выборочно 20 штук).

### [ ] ML-06 · P0 · к H+22 · «та же новость» (сценарий 2)
Для `QUERY_TYPE_NEWS_TEXT`: близость эмбеддингов + совпадение ключевых сущностей (люди, организации,
места, **числа и даты**) + LLM-проверка «Это та же новость (копия/сокращение/пересказ) или другое
событие?». Копия, сокращение, пересказ → `DIRECT` («Та же новость в сокращении»);
похожее, но другое событие → `IRRELEVANT` с объяснением («Похожая новость, но о другом ДТП: другая
дата и трасса»). Фиксированного процента совпадения нет — так и в ТЗ.

**DoD.** eval по триплетам сценария 2: исходник, сокращение, пересказ найдены; другое событие отсеяно.

### [ ] ML-07 · P1 · к H+20 · GroupPosts
**Контракт:** вход `posts: [{id, title: str|None, text}]` (до 500, уже прошедшие отбор); выход
`[{group_id: str, post_ids: [id...], representative_post_id}]`. `group_id` — любая строка, уникальная в
ответе (`"g1"`, `"g2"`…), B2 сам добавит префикс поиска. Каждый входной `id` — ровно в одной группе.

Почти дубли (одинаковый текст в разных группах) — MinHash/шинглы; пересказы — эмбеддинги +
порог + связные компоненты. `representative_post_id` — пост с самым полным текстом (дат во входе
нет). Каждый пост ровно в одной группе.

### [ ] ML-08 · P1 · к H+30 · тональность (доп. возможность)
В ответе LLM-судьи из ML-05. Без LLM — `SENTIMENT_UNSPECIFIED` (на фронте «не определена»), а не
выдуманное «нейтрально». Проверить на 30 постах руками.

### [ ] ML-09 · P0 · к H+36 · цифры и README
1. Финальный прогон eval → таблица для слайда «Качество»: precision/recall/F1 по сценариям, время
   на поиск, на пост.
2. Раздел README: какие модели и зачем, настройки (пороги, размер батча), **какие данные уходят в
   Яндекс** (текст запроса и тексты публичных постов; персональных данных пользователя — нет),
   стоимость на типичный поиск и на месяц работы агентства (оценка), что будет без ключей (фолбэк).
