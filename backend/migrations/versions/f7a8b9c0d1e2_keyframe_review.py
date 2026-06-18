"""lookframe.review + lookframe.score — keyframe quality gate

The AI verdict on a shot keyframe (identity/composition/view) persisted on the LookFrame
so a keyframe can be approved or revised BEFORE any video budget is spent.

Revision ID: f7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-18 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: str | None = 'f6a7b8c9d0e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('lookframe', sa.Column('review', sa.JSON(), nullable=True))
    op.add_column('lookframe', sa.Column('score', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('lookframe', 'score')
    op.drop_column('lookframe', 'review')
