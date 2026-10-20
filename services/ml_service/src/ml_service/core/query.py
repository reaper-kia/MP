"""Разбор запроса: эвристика (без модели, degraded) и LLM (ML-03) с теми же типами на выходе.

Тип NEWS_TEXT определяет правило (длина / число предложений), TOPIC / EVENT / PERSON — LLM,
без неё — эвристика по именам, датам и словам-событиям.
"""

import re

from pydantic import BaseModel, Field, field_validator

from ml_service.core.llm_json import ask_json
from ml_service.core.models import Entity, EntityType, QueryAnalysis, QueryType
from ml_service.core.region import REGION_STEMS, find_all_regions, find_other_places
from ml_service.core.text import WORD_RE, dates, sentences, stem, tokens, word_stems
from ml_service.providers.base import LLM

NEWS_TEXT_MIN_CHARS = 300
NEWS_TEXT_MIN_SENTENCES = 3
MAX_SEARCH_QUERIES = 8
MAX_PHRASE_CHARS = 80
MAX_SUMMARY_CHARS = 200

ROLE_WORDS = frozenset(
    stem(w)
    for w in (
        "губернатор мэр глава министр депутат председатель сенатор директор ректор"
        " прокурор начальник руководитель спикер замгубернатора вице-губернатор"
    ).split()
)
EVENT_WORDS = frozenset(
    stem(w)
    for w in (
        "открытие открылся открытия фестиваль праздник концерт выборы авария пожар матч форум"
        " конференция саммит визит презентация выставка турнир чемпионат забег митинг"
        " запуск строительство ремонт соревнования церемония"
    ).split()
)
YEAR_RE = re.compile(r"\b(19|20)\d\d\b")
# грубый признак глагола прошедшего/настоящего времени — в короткую фразу поиска не берём
VERB_ENDINGS = ("ёл", "ел", "ла", "ло", "ли", "лся", "лась", "ет", "ит", "ут", "ют", "ат", "ят")

# Многозначная тема: «безопасность» дорожная / пожарная / на воде … Нашли уточнение в запросе —
# остальные значения идут в exclude_concepts (ловушки из ТЗ и eval-набора).
AMBIGUOUS: dict[str, list[tuple[str, str]]] = {
    "безопа": [
        ("дорож", "безопасность дорожного движения"),
        ("пожар", "пожарная безопасность"),
        ("вод", "безопасность на воде"),
        ("кибер", "кибербезопасность"),
        ("информ", "информационная безопасность"),
        ("промыш", "промышленная безопасность"),
        ("пищев", "пищевая безопасность"),
    ],
}
CLARIFY_HINTS = {
    "безопа": (
        "Уточните тему: дорожная, пожарная, информационная безопасность, безопасность на воде…"
    ),
}
DEFAULT_CLARIFY_HINT = "Уточните запрос: о чём именно, где и когда (например, «ДТП в Ачинске»)"
# Слова, которые сами по себе темы не задают: «новости», «новости Красноярска», «что нового».
# Если кроме них (и региона) в запросе ничего нет — просим уточнить, а не ищем «всё подряд».
GENERIC_STEMS = frozenset(
    stem(w)
    for w in (
        "новости новость события событие информация инфо публикации посты главное сегодня"
        " вчера свежие последние интересное что нового происходит всё все"
    ).split()
)


# «в любом регионе», «по всей России»… — поиск и так по Красноярскому краю, такие уточнения лишние
_OTHER_REGIONS = re.compile(
    r",?\s*(?:или\s+)?(?:в\s+любом\s+регионе|по\s+всей\s+россии|в\s+каком\s+регионе"
    r"|по\s+всей\s+стране)\b",
    re.IGNORECASE,
)


def _clean_clarification_hint(hint: str) -> str:
    """Убирает из подсказки уточнения про другие регионы: регион по умолчанию — край."""
    if not hint:
        return ""
    return _OTHER_REGIONS.sub("", hint).strip(" ,.-—")


# ─────────────────────────── эвристика ───────────────────────────


def detect_query_type(query: str) -> QueryType:
    """Только правило NEWS_TEXT — его не отдаём модели (так в ML.md)."""
    text = query.strip()
    if len(text) > NEWS_TEXT_MIN_CHARS or len(list(sentences(text))) >= NEWS_TEXT_MIN_SENTENCES:
        return QueryType.NEWS_TEXT
    return QueryType.TOPIC


def _person_names(text: str) -> list[str]:
    """Последовательности ≥ 2 слов с заглавной, не места: «Михаил Котюков»."""
    names: list[str] = []
    current: list[str] = []
    for m in WORD_RE.finditer(text + " ."):
        word = m.group(0)
        is_name = (
            word[:1].isupper()
            and not word.isupper()
            and len(word) > 2
            and stem(word) not in REGION_STEMS
            and not find_all_regions(word)
            and not find_other_places(word)
        )
        if is_name:
            current.append(word)
            continue
        if len(current) >= 2:
            names.append(" ".join(current))
        current = []
    return names


def _surname_after_role(text: str) -> str:
    """«губернатор Котюков» → «Котюков»."""
    words = [m.group(0) for m in WORD_RE.finditer(text)]
    for prev, word in zip(words, words[1:], strict=False):
        if stem(prev) in ROLE_WORDS and word[:1].isupper() and not find_all_regions(word):
            return word
    return ""


def _heuristic_entities(text: str) -> list[Entity]:
    entities = [Entity(name, EntityType.PERSON) for name in _person_names(text)]
    surname = _surname_after_role(text)
    if surname and not any(surname in e.text for e in entities):
        entities.append(Entity(surname, EntityType.PERSON))
    places = find_all_regions(text) + find_other_places(text)
    entities += [Entity(p, EntityType.LOCATION) for p in places]
    for m in re.finditer(r"\b\d{1,2}\s+[а-яё]+\b", text, re.IGNORECASE):
        if dates(m.group(0)):
            entities.append(Entity(m.group(0), EntityType.DATE))
    return entities


def _core_phrase(text: str) -> str:
    """Запрос без региона: «Безопасность дорожного движения» — короче, лучше для поиска."""
    cut = re.sub(
        r"\s*\b(в|во|по|на)\s+(красноярск\w*\s+кра\w+|красноярск\w*|крае|регионе)\b.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return cut.strip(" ,.-—") or text


def _ambiguity(text: str) -> tuple[list[str], list[str], str]:
    """(must, exclude, hint) по таблице многозначных тем."""
    query_stems = word_stems(text)
    for head, variants in AMBIGUOUS.items():
        if not any(s.startswith(head) for s in query_stems):
            continue
        chosen = [
            concept
            for qualifier, concept in variants
            if any(s.startswith(qualifier) and not s.startswith(head) for s in query_stems)
        ]
        if not chosen:
            return [], [], CLARIFY_HINTS.get(head, DEFAULT_CLARIFY_HINT)
        others = [concept for _, concept in variants if concept not in chosen]
        return chosen, others, ""
    return [], [], ""


def analyze_query_heuristic(query: str) -> QueryAnalysis:
    text = " ".join(query.split())
    if detect_query_type(text) is QueryType.NEWS_TEXT:
        return _news_text_heuristic(query)

    entities = _heuristic_entities(text)
    persons = [e.text for e in entities if e.type is EntityType.PERSON]
    meaningful = word_stems(text) - REGION_STEMS
    topical = meaningful - GENERIC_STEMS
    must, exclude, hint = _ambiguity(text)
    if len(meaningful) >= 2:
        hint = ""

    if persons:
        query_type = QueryType.PERSON
        surname = persons[0].split()[-1]
        must = [surname]
        summary = f"Человек: {persons[0]} — упоминания"
        search_queries = [persons[0], surname, _core_phrase(text)]
    else:
        has_event = bool(
            dates(text)
            or YEAR_RE.search(text)
            or {stem(t.text) for t in tokens(text)} & EVENT_WORDS
        )
        query_type = QueryType.EVENT if has_event else QueryType.TOPIC
        summary = f"{'Событие' if has_event else 'Тема'}: {text}"
        search_queries = [_core_phrase(text), text]

    hint_text = hint or ("" if topical else DEFAULT_CLARIFY_HINT)
    cleaned_hint = _clean_clarification_hint(hint_text)
    return QueryAnalysis(
        query_type=query_type,
        summary=summary[:MAX_SUMMARY_CHARS],
        search_queries=_clean_phrases(search_queries),
        entities=entities,
        must_concepts=must,
        exclude_concepts=exclude,
        needs_clarification=bool(hint) or not topical,
        clarification_hint=cleaned_hint if (bool(hint) or not topical) else "",
    )


def news_title(query: str) -> str:
    first = next(iter(sentences(query)), (0, min(len(query), 120)))
    title = query[first[0] : first[1]].strip()
    if len(title) > 120:
        cut = title[:120]
        title = cut[: cut.rfind(" ")] if " " in cut else cut
    return title.rstrip(" .,!?")


def _news_text_heuristic(query: str) -> QueryAnalysis:
    title = news_title(query)
    entities = _heuristic_entities(query)
    places = [e.text for e in entities if e.type is EntityType.LOCATION]
    phrases = [title]
    # короткая фраза «о чём + место»: 3 значимых слова заголовка (не место/дата/глагол) + город
    content = [
        t.text
        for t in tokens(title)
        if not t.text.isdigit()
        and t.stem not in REGION_STEMS
        and not dates(f"1 {t.text}")
        and not t.text.lower().endswith(VERB_ENDINGS)
    ][:3]
    if content:
        head = " ".join(content)
        phrases.append(f"{head} {places[0]}" if places else head)
    return QueryAnalysis(
        query_type=QueryType.NEWS_TEXT,
        summary=f"Текст новости: «{title}» — ищем её размещения"[:MAX_SUMMARY_CHARS],
        search_queries=_clean_phrases(phrases),
        entities=entities,
    )


def _clean_phrases(phrases: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for phrase in phrases:
        p = " ".join(str(phrase).split()).strip(" .,;:«»\"'")
        if len(p) > MAX_PHRASE_CHARS:
            cut = p[:MAX_PHRASE_CHARS]
            p = cut[: cut.rfind(" ")] if " " in cut else cut
        if p and p.lower() not in seen:
            seen.add(p.lower())
            result.append(p)
    return result[:MAX_SEARCH_QUERIES]


# ─────────────────────────── LLM ───────────────────────────

SYSTEM_PROMPT = """Ты помогаешь агентству печати Красноярского края искать публикации в соцсетях \
(ВКонтакте, Одноклассники, MAX). Пользователь ввёл запрос. Разбери его и верни ТОЛЬКО JSON:
{
 "query_type": "topic" | "event" | "person",
 "summary": "одна фраза для пользователя: как ты понял запрос",
 "search_queries": ["3-8 коротких фраз по 1-4 слова для лексического поиска ВКонтакте"],
 "entities": [{"text": "...", "type": "person|organization|location|event|date|number"}],
 "must_concepts": ["без чего пост точно не подходит"],
 "exclude_concepts": ["что часто путают с запросом и надо отсекать"],
 "needs_clarification": false,
 "clarification_hint": ""
}
Правила:
- topic — тема; event — конкретное событие (дата, место, «открытие», «авария»…); \
person — человек.
- search_queries влияют на полноту: поиск ищет слова буквально. Дай синонимы, аббревиатуры и \
разговорные формы: «ДТП», «авария», «ГИБДД», «Госавтоинспекция», «пешеходный переход». Можно \
добавлять город или край. Не повторяй одну фразу в разных падежах.
- exclude_concepts — только явные ловушки многозначных слов («пожарная безопасность» для \
дорожной). Если ловушек нет — пустой список.
- needs_clarification = true, только если запрос из одного общего слова; тогда в \
clarification_hint предложи варианты («Уточните тему: дорожная, пожарная, информационная…»).
- Не предлагай искать «в любом регионе» или «по всей России» — поиск по умолчанию ведётся \
по Красноярскому краю.
- Пиши по-русски. Ничего не выдумывай про конкретные новости."""

EXAMPLE = """Пример. Запрос: «Безопасность дорожного движения в Красноярском крае»
{"query_type": "topic", "summary": "Тема: безопасность дорожного движения (ДТП, ГИБДД, пешеходы) \
в Красноярском крае", "search_queries": ["безопасность дорожного движения", "ДТП Красноярск", \
"Госавтоинспекция Красноярский край", "пешеходный переход", "рейд ГИБДД"], "entities": \
[{"text": "Красноярский край", "type": "location"}], "must_concepts": ["дорожное движение"], \
"exclude_concepts": ["пожарная безопасность", "безопасность на воде"], "needs_clarification": \
false, "clarification_hint": ""}"""

NEWS_SYSTEM_PROMPT = """Ты помогаешь агентству печати Красноярского края найти, где в соцсетях \
перепечатали новость (копии, сокращения, пересказы). Пользователь вставил текст новости. \
Верни ТОЛЬКО JSON:
{
 "summary": "одна фраза: о чём новость (что, где, когда)",
 "search_queries": ["3-8 коротких фраз по 2-5 слов: ключевые сочетания новости, по которым её \
найдёт буквальный поиск ВКонтакте; заголовок можно"],
 "entities": [{"text": "...", "type": "person|organization|location|event|date|number"}],
 "must_concepts": ["2-4 главных факта новости: событие, объект, место"]
}
В entities обязательно все люди, организации, места, даты и числа из текста — так отличаем ту же \
новость от похожей. Пиши по-русски, ничего не добавляй от себя."""


class _LlmEntity(BaseModel):
    text: str
    type: str


class _LlmAnalysis(BaseModel):
    query_type: str = "topic"
    summary: str = ""
    search_queries: list[str] = Field(default_factory=list)
    entities: list[_LlmEntity] = Field(default_factory=list)
    must_concepts: list[str] = Field(default_factory=list)
    exclude_concepts: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_hint: str = ""

    @field_validator("search_queries", "must_concepts", "exclude_concepts", mode="before")
    @classmethod
    def _strings(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(v) for v in value if isinstance(v, (str, int, float)) and str(v).strip()]
        return []

    @field_validator("entities", mode="before")
    @classmethod
    def _entities(cls, value: object) -> list[object]:
        return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


ENTITY_ALIASES = {t.value: t for t in EntityType} | {
    "org": EntityType.ORGANIZATION,
    "loc": EntityType.LOCATION,
    "place": EntityType.LOCATION,
    "geo": EntityType.LOCATION,
    "time": EntityType.DATE,
    "money": EntityType.NUMBER,
    "quantity": EntityType.NUMBER,
}
LLM_TYPES = {"topic": QueryType.TOPIC, "event": QueryType.EVENT, "person": QueryType.PERSON}


async def analyze_query_llm(llm: LLM, query: str, base: QueryAnalysis) -> QueryAnalysis:
    """base — эвристика по тому же запросу: из неё добираем то, что модель не дала.

    MlUnavailableError / LlmAnswerError пробрасываются — фолбэк решает engine.
    """
    is_news = base.query_type is QueryType.NEWS_TEXT
    if is_news:
        answer = await ask_json(
            llm, NEWS_SYSTEM_PROMPT, f"Текст новости:\n{query}", _LlmAnalysis, max_tokens=700
        )
    else:
        user = f"{EXAMPLE}\n\nЗапрос: «{query}»"
        answer = await ask_json(llm, SYSTEM_PROMPT, user, _LlmAnalysis, max_tokens=700)
    return merge_analysis(answer, base, query)


def merge_analysis(answer: _LlmAnalysis, base: QueryAnalysis, query: str) -> QueryAnalysis:
    is_news = base.query_type is QueryType.NEWS_TEXT
    query_type = base.query_type if is_news else LLM_TYPES.get(answer.query_type.strip().lower())
    if query_type is None:
        query_type = base.query_type

    if is_news:
        phrases = [*base.search_queries[:1], *answer.search_queries, *base.search_queries[1:]]
    else:
        phrases = [*answer.search_queries, *base.search_queries]

    candidates: list[tuple[str, EntityType | None]] = [
        (e.text, ENTITY_ALIASES.get(e.type.strip().lower())) for e in answer.entities
    ] + [(e.text, e.type) for e in base.entities]
    entities: list[Entity] = []
    seen: set[tuple[str, EntityType]] = set()
    for raw_text, etype in candidates:
        text = raw_text.strip()
        if etype is None or not text or (text.lower(), etype) in seen:
            continue
        seen.add((text.lower(), etype))
        entities.append(Entity(text[:100], etype))

    # «нужно уточнить» — только для действительно короткого запроса: модель любит перестраховаться
    short = len(word_stems(query) - REGION_STEMS) <= 2
    needs_clarification = base.needs_clarification or (answer.needs_clarification and short)
    raw_hint = answer.clarification_hint.strip() or base.clarification_hint
    hint = _clean_clarification_hint(raw_hint)
    summary = " ".join(answer.summary.split())[:MAX_SUMMARY_CHARS] or base.summary
    must = _clean_list(answer.must_concepts) or base.must_concepts
    if query_type is QueryType.PERSON and base.query_type is QueryType.PERSON:
        must = list(dict.fromkeys([*base.must_concepts, *must]))

    return QueryAnalysis(
        query_type=query_type,
        summary=summary,
        search_queries=_clean_phrases(phrases),
        entities=entities,
        must_concepts=must,
        exclude_concepts=list(
            dict.fromkeys([*_clean_list(answer.exclude_concepts), *base.exclude_concepts])
        ),
        needs_clarification=needs_clarification,
        clarification_hint=hint if needs_clarification else "",
    )


def _clean_list(values: list[str]) -> list[str]:
    return [v.strip()[:MAX_PHRASE_CHARS] for v in values if v.strip()][:MAX_SEARCH_QUERIES]
