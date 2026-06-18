"""shot.vo_asset_id — synthesized voiceover audio asset per shot

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-06-18 14:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: str | None = 'c0d1e2f3a4b5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'shot', sa.Column('vo_asset_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('shot', 'vo_asset_id')
