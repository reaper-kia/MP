from __future__ import annotations

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from search_service.domain.entities import Publication, Search, SearchResult, SearchTarget, Source
from search_service.domain.value_objects import Period
from search_service.infra.database.models import (
    PublicationModel,
    SearchModel,
    SearchResultModel,
    SearchTargetModel,
    SourceModel,
)


def _source_to_entity(m: SourceModel) -> Source:
    return Source(
        platform=m.platform,
        external_id=m.external_id,
        screen_name=m.screen_name,
        url=m.url,
        name=m.name,
        city=m.city,
        is_regional=m.is_regional,
        is_active=m.is_active,
        notes=m.notes,
        id=m.id,
        deleted_at=m.deleted_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _search_to_entity(m: SearchModel) -> Search:
    return Search(
        query=m.query,
        period=Period(from_date=m.period_from, to_date=m.period_to),
        mode=m.mode,
        platforms=m.platforms,
        source_ids=m.source_ids,
        id=m.id,
        query_type=m.query_type,
        query_analysis=m.query_analysis,
        status=m.status,
        stage=m.stage,
        warnings=m.warnings or [],
        created_at=m.created_at,
        started_at=m.started_at,
        finished_at=m.finished_at,
    )


def _target_to_entity(m: SearchTargetModel) -> SearchTarget:
    return SearchTarget(
        kind=m.kind,
        platform=m.platform,
        name=m.name,
        url=m.url,
        source_id=m.source_id,
        id=m.id,
        search_id=m.search_id,
        status=m.status,
        fetched=m.fetched,
        matched=m.matched,
        attempts=m.attempts,
        error_code=m.error_code,
        error_message=m.error_message,
        started_at=m.started_at,
        finished_at=m.finished_at,
    )


def _pub_to_entity(m: PublicationModel) -> Publication:
    return Publication(
        platform=m.platform,
        source_external_id=m.source_external_id,
        post_external_id=m.post_external_id,
        url=m.url,
        source_name=m.source_name,
        source_url=m.source_url,
        text=m.text,
        title=m.title,
        published_at=m.published_at,
        metrics=m.metrics,
        is_repost=m.is_repost,
        repost_of_url=m.repost_of_url,
        id=m.id,
        first_seen_at=m.first_seen_at,
        last_seen_at=m.last_seen_at,
    )


def _result_to_entity(m: SearchResultModel) -> SearchResult:
    from search_service.domain.enums import DateStatus, Relevance

    return SearchResult(
        search_id=m.search_id,
        publication_id=m.publication_id,
        target_id=m.target_id,
        relevance=Relevance(m.relevance) if m.relevance else None,
        score=m.score,
        explanation=m.explanation,
        region_by_source=m.region_by_source,
        region_by_content=m.region_by_content,
        region_evidence=m.region_evidence,
        sentiment=m.sentiment,
        excerpt_start=m.excerpt_start,
        excerpt_end=m.excerpt_end,
        highlights=m.highlights or [],
        group_id=m.group_id,
        date_status=DateStatus(m.date_status),
        excluded=m.excluded,
        excluded_at=m.excluded_at,
        id=m.id,
    )


class SourceRepo:
    def __init__(self, s: AsyncSession):
        self.s = s

    async def get_by_id(self, source_id):
        r = await self.s.execute(select(SourceModel).where(SourceModel.id == source_id))
        m = r.scalar_one_or_none()
        return _source_to_entity(m) if m else None

    async def get_by_key(self, platform, external_id):
        r = await self.s.execute(
            select(SourceModel).where(
                SourceModel.platform == platform,
                SourceModel.external_id == external_id,
                SourceModel.deleted_at.is_(None),
            )
        )
        m = r.scalar_one_or_none()
        return _source_to_entity(m) if m else None

    async def get_by_ids(self, ids):
        if not ids:
            return []
        r = await self.s.execute(
            select(SourceModel).where(SourceModel.id.in_(ids), SourceModel.deleted_at.is_(None))
        )
        return [_source_to_entity(m) for m in r.scalars().all()]

    async def list(self, *, platforms=None, q=None, is_active=None, limit=50, offset=0):
        stmt = select(SourceModel).where(SourceModel.deleted_at.is_(None))
        if platforms:
            stmt = stmt.where(SourceModel.platform.in_(platforms))
        if is_active is not None:
            stmt = stmt.where(SourceModel.is_active == is_active)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(SourceModel.name.ilike(like), SourceModel.url.ilike(like)))
        # total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.s.execute(count_stmt)).scalar_one()
        # page
        stmt = stmt.order_by(SourceModel.created_at.desc()).offset(offset).limit(limit)
        r = await self.s.execute(stmt)
        return [_source_to_entity(m) for m in r.scalars().all()], total

    async def add(self, e: Source):
        m = SourceModel(
            id=e.id,
            platform=e.platform,
            external_id=e.external_id,
            screen_name=e.screen_name,
            url=e.url,
            name=e.name,
            city=e.city,
            is_regional=e.is_regional,
            is_active=e.is_active,
            notes=e.notes,
            created_at=e.created_at,
            updated_at=e.updated_at,
        )
        self.s.add(m)

    async def save(self, e: Source):
        await self.s.execute(
            update(SourceModel)
            .where(SourceModel.id == e.id)
            .values(
                name=e.name,
                city=e.city,
                is_regional=e.is_regional,
                is_active=e.is_active,
                notes=e.notes,
                deleted_at=e.deleted_at,
                updated_at=e.updated_at,
            )
        )


class SearchRepo:
    def __init__(self, s: AsyncSession):
        self.s = s

    async def get_by_id(self, search_id):
        r = await self.s.execute(select(SearchModel).where(SearchModel.id == search_id))
        m = r.scalar_one_or_none()
        return _search_to_entity(m) if m else None

    async def get_with_targets(self, search_id):
        r = await self.s.execute(select(SearchModel).where(SearchModel.id == search_id))
        m = r.scalar_one_or_none()
        if not m:
            return None
        e = _search_to_entity(m)
        tr = await self.s.execute(
            select(SearchTargetModel).where(SearchTargetModel.search_id == search_id)
        )
        e.targets = [_target_to_entity(t) for t in tr.scalars().all()]
        return e

    async def list(self, *, limit=50, offset=0):
        count_stmt = select(func.count()).select_from(SearchModel)
        total = (await self.s.execute(count_stmt)).scalar_one()
        stmt = (
            select(SearchModel).order_by(SearchModel.created_at.desc()).offset(offset).limit(limit)
        )
        r = await self.s.execute(stmt)
        items = [_search_to_entity(m) for m in r.scalars().all()]
        return items, total, offset + len(items) < total

    async def list_running_or_queued(self):
        r = await self.s.execute(
            select(SearchModel).where(SearchModel.status.in_(["queued", "running"]))
        )
        return [_search_to_entity(m) for m in r.scalars().all()]

    async def add(self, e: Search):
        m = SearchModel(
            id=e.id,
            query=e.query,
            period_from=e.period.from_date,
            period_to=e.period.to_date,
            mode=e.mode,
            platforms=e.platforms,
            source_ids=e.source_ids,
            query_type=e.query_type,
            query_analysis=e.query_analysis,
            status=e.status,
            stage=e.stage,
            warnings=e.warnings,
            created_at=e.created_at,
            started_at=e.started_at,
            finished_at=e.finished_at,
        )
        self.s.add(m)

    async def save(self, e: Search):
        await self.s.execute(
            update(SearchModel)
            .where(SearchModel.id == e.id)
            .values(
                query_type=e.query_type,
                query_analysis=e.query_analysis,
                status=e.status,
                stage=e.stage,
                warnings=e.warnings,
                started_at=e.started_at,
                finished_at=e.finished_at,
            )
        )


class TargetRepo:
    def __init__(self, s: AsyncSession):
        self.s = s

    async def list_by_search(self, search_id):
        r = await self.s.execute(
            select(SearchTargetModel).where(SearchTargetModel.search_id == search_id)
        )
        return [_target_to_entity(m) for m in r.scalars().all()]

    async def add(self, e: SearchTarget):
        m = SearchTargetModel(
            id=e.id,
            search_id=e.search_id,
            kind=e.kind,
            platform=e.platform,
            source_id=e.source_id,
            name=e.name,
            url=e.url,
            status=e.status,
            fetched=e.fetched,
            matched=e.matched,
            attempts=e.attempts,
            error_code=e.error_code,
            error_message=e.error_message,
            started_at=e.started_at,
            finished_at=e.finished_at,
        )
        self.s.add(m)

    async def save(self, e: SearchTarget):
        await self.s.execute(
            update(SearchTargetModel)
            .where(SearchTargetModel.id == e.id)
            .values(
                status=e.status,
                fetched=e.fetched,
                matched=e.matched,
                attempts=e.attempts,
                error_code=e.error_code,
                error_message=e.error_message,
                started_at=e.started_at,
                finished_at=e.finished_at,
            )
        )

    async def get_by_ids(self, ids):
        if not ids:
            return []
        r = await self.s.execute(select(SearchTargetModel).where(SearchTargetModel.id.in_(ids)))
        return [_target_to_entity(m) for m in r.scalars().all()]


class PublicationRepo:
    def __init__(self, s: AsyncSession):
        self.s = s

    async def get_by_key(self, platform, source_external_id, post_external_id):
        r = await self.s.execute(
            select(PublicationModel).where(
                PublicationModel.platform == platform,
                PublicationModel.source_external_id == source_external_id,
                PublicationModel.post_external_id == post_external_id,
            )
        )
        m = r.scalar_one_or_none()
        return _pub_to_entity(m) if m else None

    async def get_by_ids(self, ids):
        if not ids:
            return []
        r = await self.s.execute(select(PublicationModel).where(PublicationModel.id.in_(ids)))
        return [_pub_to_entity(m) for m in r.scalars().all()]

    async def upsert(self, e: Publication) -> Publication:
        existing = await self.get_by_key(e.platform, e.source_external_id, e.post_external_id)
        if existing:
            existing.merge_from(e)
            await self.s.execute(
                update(PublicationModel)
                .where(PublicationModel.id == existing.id)
                .values(
                    url=existing.url,
                    source_name=existing.source_name,
                    source_url=existing.source_url,
                    text=existing.text,
                    title=existing.title,
                    published_at=existing.published_at,
                    metrics=existing.metrics,
                    last_seen_at=existing.last_seen_at,
                )
            )
            return existing
        m = PublicationModel(
            id=e.id,
            platform=e.platform,
            source_external_id=e.source_external_id,
            post_external_id=e.post_external_id,
            url=e.url,
            source_name=e.source_name,
            source_url=e.source_url,
            text=e.text,
            title=e.title,
            published_at=e.published_at,
            metrics=e.metrics,
            is_repost=e.is_repost,
            repost_of_url=e.repost_of_url,
            first_seen_at=e.first_seen_at,
            last_seen_at=e.last_seen_at,
        )
        self.s.add(m)
        return e


class ResultRepo:
    def __init__(self, s: AsyncSession):
        self.s = s

    async def add(self, e: SearchResult):
        m = SearchResultModel(
            id=e.id,
            search_id=e.search_id,
            publication_id=e.publication_id,
            target_id=e.target_id,
            relevance=e.relevance,
            score=e.score,
            explanation=e.explanation,
            region_by_source=e.region_by_source,
            region_by_content=e.region_by_content,
            region_evidence=e.region_evidence,
            sentiment=e.sentiment,
            excerpt_start=e.excerpt_start,
            excerpt_end=e.excerpt_end,
            highlights=e.highlights,
            group_id=e.group_id,
            date_status=e.date_status,
            excluded=e.excluded,
            excluded_at=e.excluded_at,
        )
        self.s.add(m)

    async def save(self, e: SearchResult):
        await self.s.execute(
            update(SearchResultModel)
            .where(SearchResultModel.id == e.id)
            .values(
                relevance=e.relevance,
                score=e.score,
                explanation=e.explanation,
                region_by_content=e.region_by_content,
                region_evidence=e.region_evidence,
                sentiment=e.sentiment,
                excerpt_start=e.excerpt_start,
                excerpt_end=e.excerpt_end,
                highlights=e.highlights,
                group_id=e.group_id,
                excluded=e.excluded,
                excluded_at=e.excluded_at,
            )
        )

    async def get_by_search(self, search_id):
        r = await self.s.execute(
            select(SearchResultModel).where(SearchResultModel.search_id == search_id)
        )
        return [_result_to_entity(m) for m in r.scalars().all()]

    async def list_filtered(
        self,
        *,
        search_id,
        relevance=None,
        platforms=None,
        target_ids=None,
        date_status=None,
        include_excluded=False,
        sort="relevance",
        limit=50,
        offset=0,
    ):
        from search_service.domain.enums import Relevance

        # join с publications для фильтра по platform
        stmt = (
            select(SearchResultModel)
            .join(PublicationModel, SearchResultModel.publication_id == PublicationModel.id)
            .where(SearchResultModel.search_id == search_id)
        )
        # relevance IS NULL не попадает никогда
        stmt = stmt.where(SearchResultModel.relevance.is_not(None))

        if relevance:
            stmt = stmt.where(SearchResultModel.relevance.in_(relevance))
        if platforms:
            stmt = stmt.where(PublicationModel.platform.in_(platforms))
        if target_ids:
            stmt = stmt.where(SearchResultModel.target_id.in_(target_ids))
        if date_status:
            stmt = stmt.where(SearchResultModel.date_status.in_(date_status))
        if not include_excluded:
            stmt = stmt.where(SearchResultModel.excluded == False)

        # сортировка
        if sort == "date_desc":
            stmt = stmt.order_by(PublicationModel.published_at.desc().nullslast())
        elif sort == "date_asc":
            stmt = stmt.order_by(PublicationModel.published_at.asc().nullslast())
        else:  # relevance
            relevance_order = case(
                (SearchResultModel.relevance == Relevance.DIRECT, 1),
                (SearchResultModel.relevance == Relevance.INDIRECT, 2),
                (SearchResultModel.relevance == Relevance.DISPUTED, 3),
                else_=4,
            )
            stmt = stmt.order_by(
                relevance_order,
                SearchResultModel.score.desc().nullslast(),
                PublicationModel.published_at.desc().nullslast(),
            )

        # total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.s.execute(count_stmt)).scalar_one()

        # page
        stmt = stmt.offset(offset).limit(limit)
        r = await self.s.execute(stmt)
        items = [_result_to_entity(m) for m in r.scalars().all()]
        return items, total, offset + len(items) < total

    async def counts(self, search_id):
        """Один SQL со всеми счётчиками через FILTER."""
        from search_service.domain.enums import DateStatus, Relevance

        stmt = select(
            func.count()
            .filter(
                and_(
                    SearchResultModel.relevance.in_(
                        [Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED]
                    ),
                    SearchResultModel.excluded == False,
                )
            )
            .label("total"),
            func.count()
            .filter(
                and_(
                    SearchResultModel.relevance == Relevance.DIRECT,
                    SearchResultModel.excluded == False,
                )
            )
            .label("direct"),
            func.count()
            .filter(
                and_(
                    SearchResultModel.relevance == Relevance.INDIRECT,
                    SearchResultModel.excluded == False,
                )
            )
            .label("indirect"),
            func.count()
            .filter(
                and_(
                    SearchResultModel.relevance == Relevance.DISPUTED,
                    SearchResultModel.excluded == False,
                )
            )
            .label("disputed"),
            func.count()
            .filter(SearchResultModel.relevance == Relevance.IRRELEVANT)
            .label("rejected"),
            func.count()
            .filter(
                and_(
                    SearchResultModel.excluded == True,
                    SearchResultModel.relevance != Relevance.IRRELEVANT,
                )
            )
            .label("excluded"),
            func.count()
            .filter(
                and_(
                    SearchResultModel.relevance.in_(
                        [Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED]
                    ),
                    SearchResultModel.excluded == False,
                    SearchResultModel.date_status == DateStatus.UNKNOWN,
                )
            )
            .label("unknown_date"),
            func.count(SearchResultModel.group_id.distinct())
            .filter(
                and_(
                    SearchResultModel.relevance.in_(
                        [Relevance.DIRECT, Relevance.INDIRECT, Relevance.DISPUTED]
                    ),
                    SearchResultModel.excluded == False,
                )
            )
            .label("groups"),
        ).where(SearchResultModel.search_id == search_id)

        r = await self.s.execute(stmt)
        row = r.one()
        return {
            "total": row.total or 0,
            "direct": row.direct or 0,
            "indirect": row.indirect or 0,
            "disputed": row.disputed or 0,
            "rejected": row.rejected or 0,
            "excluded": row.excluded or 0,
            "unknown_date": row.unknown_date or 0,
            "groups": row.groups or 0,
        }

    async def exists_in_search(self, search_id, publication_id):
        r = await self.s.execute(
            select(SearchResultModel.id)
            .where(
                SearchResultModel.search_id == search_id,
                SearchResultModel.publication_id == publication_id,
            )
            .limit(1)
        )
        return r.scalar_one_or_none() is not None
