"""add published_video

Revision ID: b7d2f4a9c1e8
Revises: e3a7c1b2d4f5
Create Date: 2026-06-01 20:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b7d2f4a9c1e8'
down_revision: str | None = 'e3a7c1b2d4f5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('published_video',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('project_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('owner_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('timeline_sequence_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('output_asset_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('aspect_ratio', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('published_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
    sa.ForeignKeyConstraint(['timeline_sequence_id'], ['timelinesequence.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_published_video_owner_id'), 'published_video', ['owner_id'], unique=False)
    op.create_index(op.f('ix_published_video_project_id'), 'published_video', ['project_id'], unique=False)
    op.create_index(
        op.f('ix_published_video_timeline_sequence_id'),
        'published_video',
        ['timeline_sequence_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_published_video_timeline_sequence_id'), table_name='published_video')
    op.drop_index(op.f('ix_published_video_project_id'), table_name='published_video')
    op.drop_index(op.f('ix_published_video_owner_id'), table_name='published_video')
    op.drop_table('published_video')
