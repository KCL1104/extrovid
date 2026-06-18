"""shot.last_keyframe_frame_id — planned closing keyframe (image-level continuity seed)

The generated CLOSING keyframe of a shot, used as the NEXT shot's first-frame seed so
shot-to-shot continuation chains through a planned image instead of the rendered video's
last frame (no serial-render dependency, no compounding drift).

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-06-18 13:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a8b9c0d1e2f3'
down_revision: str | None = 'f7a8b9c0d1e2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'shot',
        sa.Column(
            'last_keyframe_frame_id',
            sqlmodel.sql.sqltypes.AutoString(),
            sa.ForeignKey('lookframe.id'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('shot', 'last_keyframe_frame_id')
