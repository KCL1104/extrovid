"""ai-native production engine: review, routing, thumbnails, refine lineage, cut clips

- shotversion: review JSON (director notes), routing_note, thumbnail_asset_id,
  duration_sec (probed media duration)
- lookframe: parent_frame_id (Qwen-Image-Edit refine lineage)
- visualconceptset: visual_brief JSON (persisted art direction, feeds prompt composition)
- timelinesequence: clips JSON (per-clip order/trim) + options JSON (captions/music)

Revision ID: d4e8f1a2b3c6
Revises: b7d2f4a9c1e8
Create Date: 2026-06-10 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd4e8f1a2b3c6'
down_revision: str | None = 'b7d2f4a9c1e8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('shotversion', sa.Column('review', sa.JSON(), nullable=True))
    op.add_column(
        'shotversion', sa.Column('routing_note', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.add_column(
        'shotversion',
        sa.Column('thumbnail_asset_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column('shotversion', sa.Column('duration_sec', sa.Float(), nullable=True))
    op.add_column('shotversion', sa.Column('gen_params', sa.JSON(), nullable=True))
    op.add_column(
        'lookframe', sa.Column('parent_frame_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.add_column('visualconceptset', sa.Column('visual_brief', sa.JSON(), nullable=True))
    op.add_column('timelinesequence', sa.Column('clips', sa.JSON(), nullable=True))
    op.add_column('timelinesequence', sa.Column('options', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('timelinesequence', 'options')
    op.drop_column('timelinesequence', 'clips')
    op.drop_column('visualconceptset', 'visual_brief')
    op.drop_column('lookframe', 'parent_frame_id')
    op.drop_column('shotversion', 'gen_params')
    op.drop_column('shotversion', 'duration_sec')
    op.drop_column('shotversion', 'thumbnail_asset_id')
    op.drop_column('shotversion', 'routing_note')
    op.drop_column('shotversion', 'review')
