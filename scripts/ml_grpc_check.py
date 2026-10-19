"""Живая проверка ml_service по gRPC — так, как его зовёт search_service.

uv run --project services/ml_service python scripts/ml_grpc_check.py 127.0.0.1:50055

AnalyzeQuery → ScorePosts батчем из 30 постов (eval-набор БДД) → «та же новость» → GroupPosts.
Проверяет контракт (один score на пост, тот же порядок, span'ы внутри текста) и время: батч из 30
постов должен укладываться в 60 с (таймаут search_service), иначе весь батч станет «спорным».
Код выхода 0 — всё по контракту; печатает degraded (true = эвристики, false = модели).
"""

import json
import sys
import time
from collections import Counter
from pathlib import Path

import grpc
from ml.v1 import ml_service_pb2 as pb
from ml.v1 import ml_service_pb2_grpc as pb_grpc

ROOT = Path(__file__).resolve().parents[1]
TARGET = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:50055"
SCORE_LIMIT_SECONDS = 60
RELEVANCE = {v: k.removeprefix("RELEVANCE_").lower() for k, v in pb.Relevance.items()}
SENTIMENT = {v: k.removeprefix("SENTIMENT_").lower() for k, v in pb.Sentiment.items()}
failures = 0


def check(cond: bool, what: str) -> None:
    global failures
    print(("  ok   " if cond else "  FAIL ") + what)
    failures += 0 if cond else 1


def rows(name: str) -> list[dict[str, str]]:
    path = ROOT / "eval" / "datasets" / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def score(stub: pb_grpc.MlServiceStub, data: list[dict[str, str]], title: str) -> None:
    query = data[0]["query"]
    started = time.monotonic()
    aq = stub.AnalyzeQuery(pb.AnalyzeQueryRequest(query=query), timeout=20)
    print(f"\n{title}: AnalyzeQuery за {time.monotonic() - started:.1f} с, degraded={aq.degraded}")
    print(f"  понято: {aq.analysis.summary}")
    print(f"  фразы: {list(aq.analysis.search_queries)}")
    check(3 <= len(aq.analysis.search_queries) <= 8 or aq.degraded, "3–8 поисковых фраз")

    posts = [
        pb.PostForScoring(
            id=r["post_id"],
            title=r["title"],
            text=r["post_text"],
            source_name=r["source_name"],
            source_is_regional=bool(r["source_is_regional"]),
        )
        for r in data[:30]
    ]
    started = time.monotonic()
    resp = stub.ScorePosts(
        pb.ScorePostsRequest(query=query, analysis=aq.analysis, posts=posts),
        timeout=SCORE_LIMIT_SECONDS,
    )
    elapsed = time.monotonic() - started
    print(f"  ScorePosts {len(posts)} постов за {elapsed:.1f} с, degraded={resp.degraded}")
    check(elapsed < SCORE_LIMIT_SECONDS, f"батч укладывается в {SCORE_LIMIT_SECONDS} с")
    check(
        [s.id for s in resp.scores] == [p.id for p in posts], "один score на пост, тот же порядок"
    )
    spans_ok = all(
        0 <= s.excerpt_span.start < s.excerpt_span.end <= len(p.text)
        and s.excerpt_span.end - s.excerpt_span.start <= 300
        and all(0 <= h.start < h.end <= len(p.text) for h in s.highlight_spans)
        for s, p in zip(resp.scores, posts, strict=True)
    )
    check(spans_ok, "выдержка и подсветка внутри текста, выдержка ≤ 300")
    check(all(0 < len(s.explanation) <= 150 for s in resp.scores), "объяснение 1–150 символов")
    print(f"  классы: {dict(Counter(RELEVANCE[s.relevance] for s in resp.scores))}")
    print(f"  тональность: {dict(Counter(SENTIMENT[s.sentiment] for s in resp.scores))}")
    hits = sum(
        1
        for s, r in zip(resp.scores, data, strict=False)
        if (RELEVANCE[s.relevance] in {"direct", "indirect", "disputed"})
        == (r["label"] in {"direct", "indirect"})
    )
    print(f"  совпало с разметкой «найдено / не найдено»: {hits} из {len(resp.scores)}")
    for s, r in list(zip(resp.scores, data, strict=False))[:3]:
        print(f"  · [{RELEVANCE[s.relevance]}] {r['post_text'][:60]!r} — {s.explanation}")


def main() -> int:
    print(f"ml_service по gRPC: {TARGET}")
    with grpc.insecure_channel(TARGET) as channel:
        grpc.channel_ready_future(channel).result(timeout=15)
        stub = pb_grpc.MlServiceStub(channel)
        score(stub, rows("bdd_krasnoyarsk"), "Тема (БДД)")
        news = rows("news_text")
        score(stub, news, "Текст новости")

        started = time.monotonic()
        groups = stub.GroupPosts(
            pb.GroupPostsRequest(
                posts=[
                    pb.PostForGrouping(id=r["post_id"], title=r["title"], text=r["post_text"])
                    for r in news
                ]
            ),
            timeout=60,
        ).groups
        print(f"\nGroupPosts {len(news)} постов за {time.monotonic() - started:.1f} с")
        ids = sorted(pid for g in groups for pid in g.post_ids)
        check(ids == sorted(r["post_id"] for r in news), "каждый пост ровно в одной группе")
        group_of = {pid: g.group_id for g in groups for pid in g.post_ids}
        same = {group_of[r["post_id"]] for r in news if r["label"] == "direct"}
        check(len(same) == 1, "копия, сокращение и пересказ — один сюжет")

        try:
            stub.ScorePosts(
                pb.ScorePostsRequest(query="x" * 5, posts=[pb.PostForScoring(id="a")] * 2),
                timeout=10,
            )
            check(False, "дубли id → INVALID_ARGUMENT")
        except grpc.RpcError as e:
            check(e.code() == grpc.StatusCode.INVALID_ARGUMENT, "дубли id → INVALID_ARGUMENT")

    print("\nAll good" if not failures else f"\n{failures} проверок не прошли")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
