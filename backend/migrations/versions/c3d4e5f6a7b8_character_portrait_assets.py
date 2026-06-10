"""characterprofile.portrait_assets — canonical multi-view turnaround (ViMax PR-D)

{"front": asset_id, "side": asset_id, "back": asset_id} — clean white-background
portraits used as the identity anchor for r2v reference sets.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-10 19:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('characterprofile', sa.Column('portrait_assets', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('characterprofile', 'portrait_assets')
