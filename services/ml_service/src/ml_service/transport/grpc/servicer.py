from ml.v1 import ml_service_pb2 as pb
from ml.v1 import ml_service_pb2_grpc as pb_grpc

from ml_service.engine import MlEngine
from ml_service.transport.grpc.errors import Context, grpc_errors
from ml_service.transport.grpc.mappers import (
    analysis_from_proto,
    analysis_to_proto,
    group_input_from_proto,
    group_to_proto,
    post_from_proto,
    score_to_proto,
)


class MlServicer(pb_grpc.MlServiceServicer):
    """Только перевод proto ⇄ engine. Логики здесь нет."""

    def __init__(self, engine: MlEngine) -> None:
        self._engine = engine

    @grpc_errors
    async def AnalyzeQuery(
        self, request: pb.AnalyzeQueryRequest, context: Context
    ) -> pb.AnalyzeQueryResponse:
        analysis, degraded = await self._engine.analyze_query(request.query)
        return pb.AnalyzeQueryResponse(analysis=analysis_to_proto(analysis), degraded=degraded)

    @grpc_errors
    async def ScorePosts(
        self, request: pb.ScorePostsRequest, context: Context
    ) -> pb.ScorePostsResponse:
        scores, degraded = await self._engine.score_posts(
            request.query,
            analysis_from_proto(request.analysis, request.query),
            [post_from_proto(p) for p in request.posts],
        )
        return pb.ScorePostsResponse(scores=[score_to_proto(s) for s in scores], degraded=degraded)

    @grpc_errors
    async def GroupPosts(
        self, request: pb.GroupPostsRequest, context: Context
    ) -> pb.GroupPostsResponse:
        groups = await self._engine.group_posts([group_input_from_proto(p) for p in request.posts])
        return pb.GroupPostsResponse(groups=[group_to_proto(g) for g in groups])
