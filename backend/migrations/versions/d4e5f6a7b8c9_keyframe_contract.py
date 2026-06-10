"""keyframe contract (ViMax adoption PR-F)

- shot.first_frame_desc / last_frame_desc / motion_desc / variation_type: the
  ff/lf/motion decomposition — planned opening/closing snapshots + the motion between
- shot.keyframe_frame_id: the generated keyframe LookFrame used as the i2v/r2v seed
- lookframe.concept_set_id becomes nullable (shot keyframes have no concept set)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-10 20:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = 'c3d4e5f6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'shot', sa.Column('first_frame_desc', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.add_column(
        'shot', sa.Column('last_frame_desc', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.add_column(
        'shot', sa.Column('motion_desc', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.add_column(
        'shot',
        sa.Column(
            'variation_type',
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default='small',
        ),
    )
    op.add_column(
        'shot',
        sa.Column(
            'keyframe_frame_id',
            sqlmodel.sql.sqltypes.AutoString(),
            sa.ForeignKey('lookframe.id'),
            nullable=True,
        ),
    )
    op.alter_column('lookframe', 'concept_set_id', nullable=True)


def downgrade() -> None:
    op.alter_column('lookframe', 'concept_set_id', nullable=False)
    op.drop_column('shot', 'keyframe_frame_id')
    op.drop_column('shot', 'variation_type')
    op.drop_column('shot', 'motion_desc')
    op.drop_column('shot', 'last_frame_desc')
    op.drop_column('shot', 'first_frame_desc')
