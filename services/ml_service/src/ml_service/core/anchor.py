"""Якорь темы (ML-16): есть ли в посте то, без чего он точно не о запросе.

Проблема, которую закрывает: запрос «Соревнования по спортивному программированию», а в подборке —
фестиваль ГТО с пометкой «прямая связь». Общее слово «соревнования» давало полное лексическое
совпадение, эмбеддинг по слову «спортивному» тянул к спорту, а 7B-судья видел «соревнования,
призёры» и соглашался. Ни один слой другой не поправлял.

Якорь — детерминированная проверка, не зависящая от модели:
- фразы-якоря: главные понятия (must_concepts), фразы поиска и сам запрос;
- из каждой фразы берём только «сильные» слова: без региона, дат и общих слов («соревнования»,
  «фестиваль», «новости», «участники»…) — по одному такому слову тему не узнать;
- пост «заякорен», если хотя бы одна фраза покрыта целиком: все её сильные слова есть в посте.
  Слова сравниваем по длинной основе (9 букв): «программирование» ≠ «программа»;
- запасной путь для пересказов без слов запроса: эмбеддинг уверенно близок (≥ порога high).

Без якоря пост не поднимается выше «спорной», а «мимо» от судьи становится окончательным. Полноту
не теряем: пост всё ещё в выдаче (спорная), а мусор с общими словами уходит из прямых и косвенных.
Выключатель — ANCHOR_GATE=false.
"""

import re
from dataclasses import dataclass

from ml_service.core.models import QueryAnalysis, QueryType
from ml_service.core.region import REGION_STEMS
from ml_service.core.text import long_stem, tokens

# Сами по себе тему не задают. Сравниваем по длинной основе и точно: по короткой «программа»
# совпала бы с «программированием» (обе «програ»), а это как раз главное слово запроса.
WEAK_WORDS = (
    # события и их участники
    "соревнование соревнования турнир чемпионат первенство конкурс фестиваль праздник форум"
    " конференция мероприятие событие встреча акция выставка презентация церемония открытие"
    " закрытие итоги участник участники победитель победители призер призеры призёр призёры"
    " команда команды награждение финал этап старт сезон программа проект"
    # «новости», «что нового»
    " новости новость информация публикации посты главное сегодня вчера свежие последние"
    " интересное происходит"
    # общие прилагательные
    " новый нового новая новое новые новых новом городской городские краевой краевые"
    " региональный региональные местный местные"
)
ANCHOR_STEM = 9
WEAK_STEMS = frozenset(long_stem(w, ANCHOR_STEM) for w in WEAK_WORDS.split())
_MONTH_RE = re.compile(
    r"^(январ|феврал|март|апрел|ма[йяе]$|июн|июл|август|сентябр|октябр|ноябр|декабр)",
    re.IGNORECASE,
)


def is_weak(word: str) -> bool:
    return long_stem(word, ANCHOR_STEM) in WEAK_STEMS


def strong_words(phrase: str) -> list[str]:
    """Слова фразы, по которым тему можно узнать: без региона, дат, чисел и общих слов."""
    words: list[str] = []
    for t in tokens(phrase):
        if t.text.isdigit() or _MONTH_RE.match(t.text):
            continue
        if t.stem in REGION_STEMS or is_weak(t.text):
            continue
        words.append(t.text)
    return words


def strong_stems(phrase: str) -> frozenset[str]:
    return frozenset(long_stem(w, ANCHOR_STEM) for w in strong_words(phrase))


def is_specific(phrase: str) -> bool:
    """Фраза сама по себе указывает на тему («соревнования» — нет, «хакатон» — да)."""
    return bool(strong_words(phrase))


@dataclass(frozen=True, slots=True)
class Anchors:
    phrases: tuple[frozenset[str], ...]  # длинные основы сильных слов каждой фразы
    label: str  # что назвать в объяснении: «спортивное программирование»

    @property
    def active(self) -> bool:
        return bool(self.phrases)

    @staticmethod
    def words_in(text: str) -> set[str]:
        return {long_stem(t.text, ANCHOR_STEM) for t in tokens(text) if not t.text.isdigit()}

    def coverage(self, have: set[str]) -> float:
        """Лучшая доля сильных слов одной фразы, найденных в посте (лексика v1)."""

        def covered(word: str) -> bool:
            # «олимпиад» покрывает «олимпиадн(ые)»; «программи» не покрывается «программ(а)»
            return any(h.startswith(word) for h in have)

        return max((sum(map(covered, p)) / len(p) for p in self.phrases), default=0.0)

    def found_in(self, text: str) -> bool:
        if not self.phrases:
            return True  # нечем проверять (запрос из общих слов) — не мешаем
        return self.coverage(self.words_in(text)) >= 1.0


NO_ANCHORS = Anchors((), "")


def build_anchors(query: str, analysis: QueryAnalysis) -> Anchors:
    if analysis.query_type is QueryType.NEWS_TEXT:
        return NO_ANCHORS  # «та же новость» сверяется по фактам (same_news.py)
    sources = [*analysis.must_concepts, *analysis.search_queries, query]
    phrases: list[frozenset[str]] = []
    for source in sources:
        words = strong_stems(source)
        if words and words not in phrases:
            phrases.append(words)
    specific = [m for m in analysis.must_concepts if is_specific(m)]
    label = specific[0] if specific else " ".join(strong_words(query)).lower()
    return Anchors(tuple(phrases), label)
