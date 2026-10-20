"""search cache: cached_from_search_id, cached_at (B2-20)

Revision ID: b2_20_search_cache
Revises: c5f0512fec97
Create Date: 2026-10-20 08:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2_20_search_cache"
down_revision: str | None = "c5f0512fec97"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # подборка из кэша — копия готового поиска: с какого поиска снята и когда тот завершился
    op.add_column("searches", sa.Column("cached_from_search_id", sa.UUID(), nullable=True))
    op.add_column(
        "searches", sa.Column("cached_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("searches", "cached_at")
    op.drop_column("searches", "cached_from_search_id")
