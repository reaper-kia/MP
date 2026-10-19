"""Простейшая обработка русского текста без внешних библиотек: основы слов, числа, даты, шинглы.

Основа слова: нижний регистр, ё→е, срезаем типичное окончание, оставляем ≤ 6 символов.
«дорога / дорогу / дорогах» → «дорог», «дорожного» → «дорожн». Грубо, но без словарей — смысл
дальше ловят эмбеддинги и LLM.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z0-9]+")
SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]*")
STOP_WORDS = frozenset(
    "и в во на по с со к ко о об от до из за для при про как что это так же ли не ни но а или"
    " у над под без через его ее её их они она он мы вы я все всё был была были быть будет"
    " этот эта эти том тот та те также который которая которые когда где уже еще ещё очень"
    " может могут более менее около после перед между".split()
)
STEM_LEN = 6
# длинные окончания раньше коротких; срезаем, только если от слова остаётся ≥ 4 букв
ENDINGS = tuple(
    sorted(
        (
            "иями ями ами ого его ому ему ыми ими ией иях ах ях ой ей ий ый ая яя ое ее ые ие "
            "ую юю ом ем ов ев ам ям ою ею ым им ми а я о е ы и у ю ь й"
        ).split(),
        key=len,
        reverse=True,
    )
)

MONTHS = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "ма": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}
# «10 млн» и «10 миллионов» — одна единица
UNIT_ALIASES = {"млн": "миллион", "млрд": "миллиард", "тыс": "тысяч", "ч": "час", "км": "километр"}


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    stem: str
    start: int
    end: int


def stem(word: str) -> str:
    w = word.lower().replace("ё", "е")
    if w.isdigit():
        return w
    for ending in ENDINGS:
        if w.endswith(ending) and len(w) - len(ending) >= 4:
            w = w[: -len(ending)]
            break
    # фамилии: «Котюкова / Котюкову / Котюковым» → «котюк», как «Котюков»
    if w.endswith(("ов", "ев", "ин")) and len(w) >= 6:
        w = w[:-2]
    return w[:STEM_LEN]


def tokens(text: str) -> Iterator[Token]:
    """Значимые слова (≥ 3 букв, не стоп-слова) и все числа."""
    for m in WORD_RE.finditer(text):
        word = m.group(0)
        if not word.isdigit() and (len(word) < 3 or word.lower() in STOP_WORDS):
            continue
        yield Token(word, stem(word), m.start(), m.end())


def stems(text: str) -> set[str]:
    return {t.stem for t in tokens(text)}


def word_stems(text: str) -> set[str]:
    """Основы без чисел — для сравнения «по словам»."""
    return {t.stem for t in tokens(text) if not t.text.isdigit()}


def stem_sequence(text: str) -> list[str]:
    return [t.stem for t in tokens(text)]


def shingles(text: str, size: int = 3) -> set[tuple[str, ...]]:
    seq = stem_sequence(text)
    if len(seq) < size:
        return {tuple(seq)} if seq else set()
    return {tuple(seq[i : i + size]) for i in range(len(seq) - size + 1)}


def sentences(text: str) -> Iterator[tuple[int, int]]:
    """Позиции предложений [start, end) без ведущих/хвостовых пробелов."""
    for m in SENTENCE_RE.finditer(text):
        start, end = m.start(), m.end()
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            yield start, end


def jaccard[T](a: set[T], b: set[T]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def overlap(a: set[str], b: set[str]) -> float:
    """Доля общего от меньшего множества: сокращённая копия ≈ 1."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


# ─────────────── факты для «та же новость / другое событие» ───────────────

_NUM_UNIT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:-?\s*)([А-Яа-яЁё]+)?")


def _month(word: str) -> int | None:
    w = word.lower().replace("ё", "е")
    for prefix, month in MONTHS.items():
        if prefix == "ма":
            if w in {"мая", "май", "мае"}:
                return month
            continue
        if w.startswith(prefix):
            return month
    return None


def dates(text: str) -> set[tuple[int, int]]:
    """(день, месяц): «15 октября», «15.10»."""
    found: set[tuple[int, int]] = set()
    for m in _NUM_UNIT_RE.finditer(text):
        value, word = m.group(1), m.group(2)
        if word and value.isdigit() and 1 <= int(value) <= 31:
            month = _month(word)
            if month:
                found.add((int(value), month))
    for m in re.finditer(r"\b(\d{1,2})\.(\d{1,2})(?:\.\d{2,4})?\b", text):
        day, month = int(m.group(1)), int(m.group(2))
        if 1 <= day <= 31 and 1 <= month <= 12:
            found.add((day, month))
    return found


def quantities(text: str) -> dict[str, set[str]]:
    """Числа с единицей: {«час»: {«3»}, «миллион»: {«10»}}. Даты и номера («№5») не входят."""
    found: dict[str, set[str]] = {}
    for m in _NUM_UNIT_RE.finditer(text):
        value, word = m.group(1).replace(",", "."), m.group(2)
        if not word or _month(word) or text[max(0, m.start() - 1) : m.start()] in {"№", "#"}:
            continue
        # первые 3 буквы: «час / часа / часов», «миллион / млн» (через алиас) — одна единица
        unit = UNIT_ALIASES.get(word.lower(), word.lower()).replace("ё", "е")[:3]
        found.setdefault(unit, set()).add(value)
    return found
