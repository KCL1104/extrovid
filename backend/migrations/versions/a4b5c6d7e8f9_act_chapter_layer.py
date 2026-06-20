"""act/chapter layer — Act table + scene.act_id (P3b, long-form)

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-06-20 20:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a4b5c6d7e8f9'
down_revision: str | None = 'f3a4b5c6d7e8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'act',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('project_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('hook', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('open_loop', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('summary', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_act_project_id', 'act', ['project_id'])
    op.add_column(
        'scene', sa.Column('act_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.create_index('ix_scene_act_id', 'scene', ['act_id'])
    op.create_foreign_key('scene_act_id_fkey', 'scene', 'act', ['act_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('scene_act_id_fkey', 'scene', type_='foreignkey')
    op.drop_index('ix_scene_act_id', table_name='scene')
    op.drop_column('scene', 'act_id')
    op.drop_index('ix_act_project_id', table_name='act')
    op.drop_table('act')
