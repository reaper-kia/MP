"""search owner: анонимный id браузера, история поисков у каждого своя

Revision ID: b2_21_search_owner
Revises: b2_20_search_cache
Create Date: 2026-10-20 12:40:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2_21_search_owner"
down_revision: str | None = "b2_20_search_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # старые поиски без владельца не видны ни в чьей истории (по ссылке открываются как раньше)
    op.add_column("searches", sa.Column("owner_id", sa.Text(), nullable=True))
    op.create_index("ix_searches_owner_id", "searches", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_searches_owner_id", table_name="searches")
    op.drop_column("searches", "owner_id")
