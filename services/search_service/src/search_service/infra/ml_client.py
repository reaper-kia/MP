# ml_client.py
from search_service.applications.ports.ml_client import (
    MlClient, QueryAnalysis, PostScore, PostGroup, PostForScoring,
)


class StubMl:
    async def analyze_query(self, query: str):
        return QueryAnalysis(
            query_type="topic", summary=f"Поиск по запросу: {query}",
            search_queries=[query],
        ), True  # degraded

    async def score_posts(self, *, query, analysis, posts):
        # базовый скоринг: все DISPUTED, чтобы не терялись
        scores = []
        for p in posts:
            scores.append(PostScore(
                id=p.id, relevance="disputed", score=0.5,
                explanation="Базовый ML недоступен — проверьте вручную",
                excerpt_span=(0, min(300, len(p.text))),
            ))
        return scores, True

    async def group_posts(self, posts):
        # без групп
        return [PostGroup(group_id=str(i), post_ids=[p["id"]], representative_post_id=p["id"])
                for i, p in enumerate(posts)]