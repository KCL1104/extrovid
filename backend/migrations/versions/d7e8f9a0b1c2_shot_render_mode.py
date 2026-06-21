"""shot.render_mode — still-vs-motion render selection

"video" (default) renders the shot through the video provider; "still" freezes the shot's
planned keyframe into a clip locally (low-motion beats at image cost, no video spend).

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-06-21 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd7e8f9a0b1c2'
down_revision: str | None = 'c6d7e8f9a0b1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'shot',
        sa.Column(
            'render_mode',
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default='video',
        ),
    )


def downgrade() -> None:
    op.drop_column('shot', 'render_mode')
