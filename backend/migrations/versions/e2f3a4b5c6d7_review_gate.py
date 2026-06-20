"""review gate — scene/shot approval+lock + annotation table

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-20 18:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: str | None = 'd1e2f3a4b5c6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ('scene', 'shot'):
        op.add_column(
            table,
            sa.Column('approved', sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.add_column(
            table,
            sa.Column('locked', sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.add_column(table, sa.Column('approved_at', sa.DateTime(), nullable=True))

    op.create_table(
        'annotation',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('project_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('target_kind', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('target_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('field', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('intent', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('text', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_annotation_project_id', 'annotation', ['project_id'])
    op.create_index('ix_annotation_target_id', 'annotation', ['target_id'])


def downgrade() -> None:
    op.drop_index('ix_annotation_target_id', table_name='annotation')
    op.drop_index('ix_annotation_project_id', table_name='annotation')
    op.drop_table('annotation')
    for table in ('shot', 'scene'):
        op.drop_column(table, 'approved_at')
        op.drop_column(table, 'locked')
        op.drop_column(table, 'approved')
