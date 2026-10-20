"""Качество отбора ML на размеченных наборах (ML-02, ML-09).

Запуск из корня репозитория:
    uv run --project services/ml_service python eval/run_eval.py               # stub: эвристики
    LLM_PROVIDER=ollama EMBED_PROVIDER=ollama \\
    uv run --project services/ml_service python eval/run_eval.py --details     # локальные модели

Гоняет core через MlEngine (без gRPC) так же, как search_service: AnalyzeQuery один раз на запрос,
ScorePosts батчами по 30, GroupPosts по прошедшим отбор. Пишет markdown-таблицу в eval/report.md
(её берут в README и на слайд «Качество»).

Формулы (как в docs/tasks/ML.md):
    найдено   = предсказано direct | indirect | disputed
    recall    = найдено ∩ (метка direct | indirect) / (метка direct | indirect)
    precision = найдено ∩ (метка direct | indirect) / найдено
    спорных   = доля disputed среди найденного — работа для человека
Режим --mode global (по умолчанию) повторяет правило search_service для поиска «везде»: пост
без регионального источника и без привязки к краю в тексте отсеивается.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ml_service.config import Settings
from ml_service.core.models import GroupInput, Post, PostScore, Relevance
from ml_service.dependencies import build_engine
from ml_service.engine import MlEngine

ROOT = Path(__file__).resolve().parent
BATCH = 30  # как search_service
FOUND = {Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED}
RELEVANT = {"direct", "indirect"}
SCENARIOS = {
    "bdd_krasnoyarsk": "Тема: безопасность дорожного движения",
    "event": "Событие: открытие парка",
    "person": "Человек: губернатор",
    "news_text": "Текст новости: пожар на складе",
}


@dataclass
class Row:
    query: str
    post_id: str
    title: str | None
    text: str
    source_name: str
    regional: bool
    label: str
    note: str


@dataclass
class Result:
    name: str
    rows: list[Row]
    scores: list[PostScore]
    analyze_seconds: float
    score_seconds: float
    analyze_degraded: bool
    score_degraded: bool
    summary: str
    search_queries: list[str]
    groups_ok: bool | None = None
    judge_sent: int = 0
    judge_calls: int = 0
    prompt_chars: int = 0
    similarities: list[float | None] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)


def load(path: Path) -> dict[str, list[Row]]:
    by_query: dict[str, list[Row]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        by_query[r["query"]].append(
            Row(
                query=r["query"],
                post_id=r["post_id"],
                title=r.get("title") or None,
                text=r["post_text"],
                source_name=r.get("source_name", ""),
                regional=bool(r.get("source_is_regional")),
                label=r["label"],
                note=r.get("note", ""),
            )
        )
    return by_query


def apply_global_rule(score: PostScore, row: Row) -> Relevance:
    """Правило search_service для режима «везде» (ScoringHandler._score_batch)."""
    if score.relevance is not Relevance.IRRELEVANT and not row.regional:
        if not score.region_by_content:
            return Relevance.IRRELEVANT
    return score.relevance


async def run_query(engine: MlEngine, name: str, rows: list[Row]) -> Result:
    query = rows[0].query
    t0 = time.perf_counter()
    analysis, analyze_degraded = await engine.analyze_query(query)
    t1 = time.perf_counter()
    posts = [
        Post(
            id=r.post_id,
            text=r.text,
            title=r.title,
            source_name=r.source_name,
            source_is_regional=r.regional,
        )
        for r in rows
    ]
    scores: list[PostScore] = []
    sims: list[float | None] = []
    degraded = False
    sent = calls = chars = 0
    for start in range(0, len(posts), BATCH):
        batch_scores, batch_degraded = await engine.score_posts(
            query, analysis, posts[start : start + BATCH]
        )
        scores += batch_scores
        sims += engine.last_similarities or [None] * len(batch_scores)
        degraded = degraded or batch_degraded
        stats = engine.last_judge_stats
        sent, calls, chars = sent + stats.sent, calls + stats.calls, chars + stats.prompt_chars
    t2 = time.perf_counter()
    result = Result(
        name=name,
        rows=rows,
        scores=scores,
        analyze_seconds=t1 - t0,
        score_seconds=t2 - t1,
        analyze_degraded=analyze_degraded,
        score_degraded=degraded,
        summary=analysis.summary,
        search_queries=analysis.search_queries,
        judge_sent=sent,
        judge_calls=calls,
        prompt_chars=chars,
        similarities=sims,
    )
    if name == "news_text":
        result.groups_ok = await check_groups(engine, rows)
    return result


async def check_groups(engine: MlEngine, rows: list[Row]) -> bool:
    """Сценарий 2: копия, сокращение и пересказ — в одном сюжете, другие события — не в нём."""
    groups = await engine.group_posts(
        [GroupInput(id=r.post_id, text=r.text, title=r.title) for r in rows]
    )
    group_of = {pid: g.group_id for g in groups for pid in g.post_ids}
    same = {group_of[r.post_id] for r in rows if r.label == "direct"}
    if len(same) != 1:
        return False
    (story,) = same
    return all(group_of[r.post_id] != story for r in rows if r.label == "irrelevant")


@dataclass
class Metrics:
    total: int
    recall: float
    precision: float
    f1: float
    direct_recall: float
    direct_precision: float
    direct_f1: float
    disputed_share: float
    rejected_right: float


def ratio(a: int, b: int) -> float:
    return a / b if b else 0.0


def f1(p: float, r: float) -> float:
    return 2 * p * r / (p + r) if p + r else 0.0


def metrics(pairs: list[tuple[str, Relevance]]) -> Metrics:
    found = [(label, pred) for label, pred in pairs if pred in FOUND]
    relevant = [label for label, _ in pairs if label in RELEVANT]
    hit = sum(1 for label, _ in found if label in RELEVANT)
    recall, precision = ratio(hit, len(relevant)), ratio(hit, len(found))
    pred_direct = [label for label, pred in pairs if pred is Relevance.DIRECT]
    label_direct = sum(1 for label, _ in pairs if label == "direct")
    direct_hit = sum(1 for label in pred_direct if label == "direct")
    d_recall, d_precision = ratio(direct_hit, label_direct), ratio(direct_hit, len(pred_direct))
    irrelevant = [pred for label, pred in pairs if label == "irrelevant"]
    return Metrics(
        total=len(pairs),
        recall=recall,
        precision=precision,
        f1=f1(precision, recall),
        direct_recall=d_recall,
        direct_precision=d_precision,
        direct_f1=f1(d_precision, d_recall),
        disputed_share=ratio(sum(1 for _, p in found if p is Relevance.DISPUTED), len(found)),
        rejected_right=ratio(
            sum(1 for p in irrelevant if p is Relevance.IRRELEVANT), len(irrelevant)
        ),
    )


def num(x: int) -> str:
    return f"{x:,}".replace(",", " ")


def pct(x: float) -> str:
    return f"{x * 100:.0f} %"


def render(results: list[Result], mode: str, engine: MlEngine, settings: Settings) -> str:
    lines = [
        "# Качество отбора ML (eval)",
        "",
        f"Прогон: {datetime.now():%Y-%m-%d %H:%M}, `{engine.describe}`, режим `{mode}`, "
        f"батч {BATCH}. Наборы `eval/datasets/*.jsonl` — **тексты придуманные** (подбор порогов, "
        "не замер на реальных постах).",
        "",
        "| Сценарий | Постов | Recall | Precision | F1 | Direct: recall / F1 | Спорных "
        "| Ловушки отсеяны | мс/пост | Разбор запроса | Модель |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    all_pairs: list[tuple[str, Relevance]] = []
    total_posts = 0
    total_seconds = 0.0
    for r in results:
        pairs = []
        for row, score, sim in zip(r.rows, r.scores, r.similarities, strict=True):
            pred = apply_global_rule(score, row) if mode == "global" else score.relevance
            pairs.append((row.label, pred))
            if pred.value != row.label:
                cos = f"cos={sim:.2f} " if sim is not None else ""
                r.mismatches.append(
                    f"  {row.label:>10} → {pred.value:<10} {row.text[:90]!r}\n"
                    f"{'':14}{cos}{score.explanation}"
                )
        all_pairs += pairs
        m = metrics(pairs)
        total_posts += len(pairs)
        total_seconds += r.score_seconds
        model = "эвристика" if r.score_degraded else "модель"
        lines.append(
            f"| {SCENARIOS.get(r.name, r.name)} | {m.total} | {pct(m.recall)} | "
            f"{pct(m.precision)} | {pct(m.f1)} | {pct(m.direct_recall)} / {pct(m.direct_f1)} | "
            f"{pct(m.disputed_share)} | {pct(m.rejected_right)} | "
            f"{r.score_seconds / len(pairs) * 1000:.0f} | {r.analyze_seconds:.1f} с | {model} |"
        )
    m = metrics(all_pairs)
    lines.append(
        f"| **Всего** | {m.total} | **{pct(m.recall)}** | **{pct(m.precision)}** | "
        f"**{pct(m.f1)}** | {pct(m.direct_recall)} / {pct(m.direct_f1)} | "
        f"{pct(m.disputed_share)} | {pct(m.rejected_right)} | "
        f"{total_seconds / max(1, total_posts) * 1000:.0f} | | |"
    )
    news = next((r for r in results if r.groups_ok is not None), None)
    if news is not None:
        verdict = "да" if news.groups_ok else "**нет**"
        lines += [
            "",
            f"Сценарий 2, группы: копия, сокращение и пересказ в одном сюжете, похожие новости "
            f"о других событиях — отдельно: {verdict}.",
        ]
    sent = sum(r.judge_sent for r in results)
    calls = sum(r.judge_calls for r in results)
    chars = sum(r.prompt_chars for r in results)
    if calls:
        tokens = chars // 3  # грубо: ~3 символа кириллицы на токен
        per_1000 = tokens * 1000 // max(1, total_posts)
        lines += [
            "",
            f"LLM-судья: {sent} из {total_posts} постов, {calls} вызовов, промпты ≈ {num(tokens)} "
            f"токенов (≈ {num(per_1000)} на 1000 постов). Модель локальная — денег не стоит, "
            "цена в секундах: см. «мс/пост».",
        ]
    lines += ["", "Как поняли запросы:", ""]
    for r in results:
        aq = "эвристика" if r.analyze_degraded else "LLM"
        lines.append(f"- **{SCENARIOS.get(r.name, r.name)}** ({aq}): {r.summary}")
        lines.append(f"  фразы поиска: {', '.join(r.search_queries)}")
    lines += [
        "",
        "Настройки: "
        f"LLM `{settings.llm_provider}` / `{settings.ollama_llm_model}`, судья "
        f"`{settings.ollama_judge_model or settings.ollama_llm_model}`, эмбеддинги "
        f"`{','.join(settings.embed_chain) or 'stub'}` / `{settings.ollama_embed_model}`, "
        "пачка судьи "
        f"{settings.judge_batch_size}, параллельно {settings.judge_concurrency}, бюджет ScorePosts "
        f"{settings.score_budget_seconds:.0f} с.",
        "",
    ]
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["global", "selected"], default="global")
    parser.add_argument("--report", default=str(ROOT / "report.md"))
    parser.add_argument("--details", action="store_true", help="печатать ошибки по постам")
    parser.add_argument("--only", help="один набор: bdd_krasnoyarsk | event | person | news_text")
    args = parser.parse_args()

    report_path = Path(args.report).resolve()  # до chdir: путь относительно места запуска
    os.chdir(ROOT.parent / "services" / "ml_service")  # .env сервиса, как при запуске сервиса
    settings = Settings()
    engine = build_engine(settings)
    results: list[Result] = []
    try:
        for path in sorted((ROOT / "datasets").glob("*.jsonl")):
            if args.only and path.stem != args.only:
                continue
            for rows in load(path).values():
                results.append(await run_query(engine, path.stem, rows))
    finally:
        await engine.aclose()

    report = render(results, args.mode, engine, settings)
    report_path.write_text(report, encoding="utf-8")
    print(report)
    if args.details:
        for r in results:
            if r.mismatches:
                print(f"\n── {r.name}: {len(r.mismatches)} расхождений")
                print("\n".join(r.mismatches))
    print(f"\nОтчёт: {report_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
