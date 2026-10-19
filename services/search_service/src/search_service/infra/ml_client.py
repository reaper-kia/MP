"""Заглушка ML: реализует порт MlClient без сети (ML_MODE=stub, офлайн-разработка)."""

from typing import Any

from search_service.applications.ports.ml_client import (
    PostForScoring,
    PostGroup,
    PostScore,
    QueryAnalysis,
)


class StubMl:
    is_stub = True  # пайплайн по этому флагу добавляет warning «имитация»

    async def analyze_query(self, query: str) -> tuple[QueryAnalysis, bool]:
        return QueryAnalysis(
            query_type="topic",
            summary=f"Поиск по запросу: {query}",
            search_queries=[query],
        ), True  # degraded

    async def score_posts(
        self, *, query: str, analysis: QueryAnalysis, posts: list[PostForScoring]
    ) -> tuple[list[PostScore], bool]:
        # базовый скоринг: все DISPUTED, чтобы не терялись
        scores: list[PostScore] = []
        for p in posts:
            scores.append(
                PostScore(
                    id=p.id,
                    relevance="disputed",
                    score=0.5,
                    explanation="Базовый ML недоступен — проверьте вручную",
                    excerpt_span=(0, min(300, len(p.text))),
                )
            )
        return scores, True

    async def group_posts(self, posts: list[dict[str, Any]]) -> list[PostGroup]:
        # без групп
        return [
            PostGroup(group_id=str(i), post_ids=[p["id"]], representative_post_id=p["id"])
            for i, p in enumerate(posts)
        ]
