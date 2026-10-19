from ml_service.core.models import Span
from ml_service.core.text import sentences, tokens

MAX_EXCERPT = 300


def best_excerpt(text: str, query_stems: set[str]) -> Span:
    """Предложение с наибольшим числом совпадений (+ следующие, пока влезает в 300 символов)."""
    spans = list(sentences(text))
    if not spans:
        return Span(0, min(len(text), MAX_EXCERPT))

    def hits(span: tuple[int, int]) -> int:
        return sum(1 for t in tokens(text[span[0] : span[1]]) if t.stem in query_stems)

    best = max(range(len(spans)), key=lambda i: hits(spans[i]))
    start, end = spans[best]
    for _, nxt_end in spans[best + 1 :]:
        if nxt_end - start > MAX_EXCERPT:
            break
        end = nxt_end
    if end - start > MAX_EXCERPT:
        end = start + MAX_EXCERPT
    return Span(start, end)


def highlight_spans(text: str, query_stems: set[str], within: Span | None = None) -> list[Span]:
    lo, hi = (within.start, within.end) if within else (0, len(text))
    return [
        Span(t.start, t.end)
        for t in tokens(text)
        if t.stem in query_stems and lo <= t.start and t.end <= hi
    ]
