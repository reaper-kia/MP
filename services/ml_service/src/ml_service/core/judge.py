"""LLM-судья (ML-05, ML-06, ML-08): уточняет класс, пишет объяснение и тональность.

Посты идут пачками по N в одном промпте, пачки — параллельно (с ограничением), всё — в бюджете
времени: что не успело, остаётся с оценкой v1. Кэш по (запрос, текст): повтор поиска и пост,
найденный двумя целями, второй раз в модель не идут. Модель не пишет ни текстов, ни позиций —
только класс, одно предложение объяснения и тональность.
"""

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator

from ml_service.core.llm_json import LlmAnswerError, ask_json
from ml_service.core.models import Post, QueryAnalysis, QueryType, Relevance, Sentiment
from ml_service.core.scoring import post_text, short_sentence
from ml_service.errors import MlUnavailableError
from ml_service.providers.base import LLM

logger = logging.getLogger(__name__)

CACHE_SIZE = 50_000
EXPLANATION_CHARS = 150


@dataclass(frozen=True, slots=True)
class Verdict:
    relevance: Relevance
    explanation: str
    sentiment: Sentiment | None


@dataclass(slots=True)
class JudgeStats:
    """Для логов и eval: сколько ушло в модель, сколько из кэша, сколько не успели."""

    sent: int = 0
    cached: int = 0
    failed: int = 0
    calls: int = 0
    prompt_chars: int = 0


class JudgeCache:
    def __init__(self, size: int = CACHE_SIZE) -> None:
        self._size = size
        self._data: OrderedDict[str, Verdict] = OrderedDict()

    @staticmethod
    def key(query_key: str, post: Post) -> str:
        return query_key + ":" + hashlib.sha1(post_text(post).encode("utf-8")).hexdigest()

    def get(self, key: str) -> Verdict | None:
        verdict = self._data.get(key)
        if verdict is not None:
            self._data.move_to_end(key)
        return verdict

    def put(self, key: str, verdict: Verdict) -> None:
        self._data[key] = verdict
        if len(self._data) > self._size:
            self._data.popitem(last=False)


RELEVANCE_WORDS = {
    "direct": Relevance.DIRECT,
    "прямая": Relevance.DIRECT,
    "indirect": Relevance.INDIRECT,
    "косвенная": Relevance.INDIRECT,
    "disputed": Relevance.DISPUTED,
    "спорная": Relevance.DISPUTED,
    "irrelevant": Relevance.IRRELEVANT,
    "нерелевантная": Relevance.IRRELEVANT,
    # режим «та же новость»
    "same": Relevance.DIRECT,
    "maybe": Relevance.DISPUTED,
    "different": Relevance.IRRELEVANT,
    "unrelated": Relevance.IRRELEVANT,
}
SENTIMENT_WORDS = {
    "positive": Sentiment.POSITIVE,
    "neutral": Sentiment.NEUTRAL,
    "negative": Sentiment.NEGATIVE,
}


class _Item(BaseModel):
    i: int
    relevance: str
    explanation: str = ""
    sentiment: str = ""

    @field_validator("relevance", "sentiment", mode="before")
    @classmethod
    def _lower(cls, value: object) -> str:
        return str(value or "").strip().lower()


class _Answer(BaseModel):
    items: list[_Item] = Field(default_factory=list)


TOPIC_SYSTEM = """Ты — аналитик медиамониторинга агентства печати Красноярского края. Дан запрос \
пользователя и пронумерованные посты из соцсетей. Для КАЖДОГО поста реши, как он связан с запросом:
- direct — пост прямо о теме / событии / человеке из запроса;
- indirect — связан косвенно: упоминание вскользь, смежная тема, контекст;
- disputed — не уверен, нужна проверка человеком;
- irrelevant — о другом, в том числе то же слово в другом смысле.
{type_rule}
Полнота важнее: сомневаешься между irrelevant и другим классом — ставь disputed.
explanation — ОДНО предложение по-русски до 120 символов, только по тексту поста: о чём пост \
и почему такой класс («Пост о рейде ГИБДД у школ Ачинска»). Ничего не выдумывай.
sentiment — тональность самого поста: positive, neutral или negative.
Верни ТОЛЬКО JSON: {{"items": [{{"i": 1, "relevance": "direct", "explanation": "...", \
"sentiment": "neutral"}}]}} — ровно один элемент на каждый пост, i — номер поста."""

TYPE_RULES = {
    QueryType.TOPIC: "Регион не оценивай — это делает другая проверка.",
    QueryType.EVENT: (
        "Запрос о КОНКРЕТНОМ событии: детали, ход и итоги этого события — direct; похожее, но "
        "ДРУГОЕ событие (другой город, другой объект, другая дата) — irrelevant."
    ),
    QueryType.PERSON: (
        "Запрос о КОНКРЕТНОМ человеке: пост, где он упомянут, — direct (если он в центре) или "
        "indirect (вскользь); другой человек, даже на той же должности, — irrelevant."
    ),
}

NEWS_SYSTEM = """Ты — аналитик медиамониторинга. Дан исходный текст новости и пронумерованные \
посты. Для КАЖДОГО поста реши, та же ли это новость:
- same — та же новость: копия, сокращение или пересказ того же события;
- different — похожая новость, но о ДРУГОМ событии (другое место, дата, объект, цифры);
- unrelated — вообще о другом;
- maybe — не уверен.
explanation — ОДНО предложение по-русски до 120 символов: «Та же новость в сокращении» или \
«Похожая новость, но о другом пожаре: Норильск, склад стройматериалов». Ничего не выдумывай.
sentiment — тональность поста: positive, neutral или negative.
Верни ТОЛЬКО JSON: {"items": [{"i": 1, "relevance": "same", "explanation": "...", \
"sentiment": "neutral"}]} — ровно один элемент на каждый пост."""


def query_key(query: str, analysis: QueryAnalysis) -> str:
    raw = f"{analysis.query_type}|{query}|{analysis.summary}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def _render_posts(posts: list[Post], max_chars: int) -> str:
    blocks = []
    for n, post in enumerate(posts, start=1):
        source = f" (источник: {_clip(post.source_name, 60)})" if post.source_name else ""
        blocks.append(f"[{n}]{source}\n{_clip(post_text(post), max_chars)}")
    return "\n\n".join(blocks)


def _user_prompt(query: str, analysis: QueryAnalysis, posts: list[Post], max_chars: int) -> str:
    rendered = _render_posts(posts, max_chars)
    if analysis.query_type is QueryType.NEWS_TEXT:
        return f"Исходная новость:\n{_clip(query, 2000)}\n\nПосты:\n{rendered}"
    lines = [f"Запрос: «{_clip(query, 300)}»"]
    if analysis.summary:
        lines.append(f"Как понят: {analysis.summary}")
    if analysis.must_concepts:
        lines.append("Главное: " + "; ".join(analysis.must_concepts))
    if analysis.exclude_concepts:
        lines.append("Не путать с: " + "; ".join(analysis.exclude_concepts))
    return "\n".join(lines) + f"\n\nПосты:\n{rendered}"


def _system_prompt(analysis: QueryAnalysis) -> str:
    if analysis.query_type is QueryType.NEWS_TEXT:
        return NEWS_SYSTEM
    return TOPIC_SYSTEM.format(type_rule=TYPE_RULES.get(analysis.query_type, ""))


def _verdicts(answer: _Answer, count: int) -> dict[int, Verdict]:
    result: dict[int, Verdict] = {}
    for item in answer.items:
        relevance = RELEVANCE_WORDS.get(item.relevance)
        if relevance is None or not 1 <= item.i <= count or item.i in result:
            continue
        explanation = short_sentence(item.explanation, EXPLANATION_CHARS)
        result[item.i] = Verdict(relevance, explanation, SENTIMENT_WORDS.get(item.sentiment))
    return result


async def judge_posts(
    llm: LLM,
    query: str,
    analysis: QueryAnalysis,
    posts: list[Post],
    *,
    cache: JudgeCache,
    batch_size: int,
    concurrency: int,
    max_post_chars: int,
    deadline: float,
    stats: JudgeStats | None = None,
) -> dict[str, Verdict]:
    """{post.id: Verdict} для тех, кого модель успела оценить. Никогда не бросает."""
    stats = stats if stats is not None else JudgeStats()
    qkey = query_key(query, analysis)
    verdicts: dict[str, Verdict] = {}
    todo: list[Post] = []
    for post in posts:
        cached = cache.get(JudgeCache.key(qkey, post))
        if cached is not None:
            verdicts[post.id] = cached
            stats.cached += 1
        else:
            todo.append(post)
    if not todo or not llm.available:
        stats.failed += len(todo)
        return verdicts

    system = _system_prompt(analysis)
    batches = [todo[i : i + batch_size] for i in range(0, len(todo), batch_size)]
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run(batch: list[Post]) -> None:
        async with semaphore:
            if not llm.available or time.monotonic() >= deadline:
                stats.failed += len(batch)
                return
            user = _user_prompt(query, analysis, batch, max_post_chars)
            stats.calls += 1
            stats.prompt_chars += len(system) + len(user)
            try:
                answer = await ask_json(
                    llm, system, user, _Answer, max_tokens=90 * len(batch) + 100
                )
            except (MlUnavailableError, LlmAnswerError) as e:
                logger.warning("LLM-судья: пачка из %d постов без оценки: %s", len(batch), e)
                stats.failed += len(batch)
                return
            got = _verdicts(answer, len(batch))
            for n, post in enumerate(batch, start=1):
                verdict = got.get(n)
                if verdict is None:
                    stats.failed += 1
                    continue
                verdicts[post.id] = verdict
                cache.put(JudgeCache.key(qkey, post), verdict)
                stats.sent += 1

    tasks = [asyncio.create_task(run(b)) for b in batches]
    timeout = max(0.0, deadline - time.monotonic())
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
        missed = len(todo) - sum(1 for p in todo if p.id in verdicts)
        logger.warning("LLM-судья: не успел в бюджет, %d постов остались с оценкой v1", missed)
        stats.failed = len(todo) - stats.sent
    for task in done:
        if task.exception() is not None:  # не должно случаться: run ловит свои ошибки
            logger.error("LLM-судья: необработанная ошибка", exc_info=task.exception())
    return verdicts
