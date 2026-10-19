"""Простейшая обработка русского текста без внешних библиотек.

Это опора эвристик ML-01. В ML-04 заменить stem() на лемматизацию (pymorphy3) —
остальной код менять не придётся.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z0-9]+")
SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]*")
STOP_WORDS = frozenset(
    "и в во на по с со к ко о об от до из за для при про как что это так же ли не ни но а или"
    " у над под без через его ее её их они она он мы вы я все всё был была были быть будет".split()
)
STEM_LEN = 6


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    stem: str
    start: int
    end: int


def stem(word: str) -> str:
    """Грубая «основа»: нижний регистр, ё→е, первые 6 символов."""
    return word.lower().replace("ё", "е")[:STEM_LEN]


def tokens(text: str) -> Iterator[Token]:
    for m in WORD_RE.finditer(text):
        word = m.group(0)
        if len(word) < 3 or word.lower() in STOP_WORDS:
            continue
        yield Token(word, stem(word), m.start(), m.end())


def stems(text: str) -> set[str]:
    return {t.stem for t in tokens(text)}


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
