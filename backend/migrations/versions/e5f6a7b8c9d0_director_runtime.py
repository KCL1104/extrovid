"""director runtime: staleness flags + director chat turns (ViMax PR-H)

- scene.stale / visualconceptset.stale / shot.stale: upstream changes mark
  downstream artifacts for replanning instead of silently orphaning them
- directorturn: flat-text director chat history

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-10 21:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ('scene', 'visualconceptset', 'shot'):
        op.add_column(
            table,
            sa.Column('stale', sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.create_table(
        'directorturn',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), primary_key=True),
        sa.Column(
            'project_id',
            sqlmodel.sql.sqltypes.AutoString(),
            sa.ForeignKey('project.id'),
            nullable=False,
            index=True,
        ),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('content', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('directorturn')
    for table in ('shot', 'visualconceptset', 'scene'):
        op.drop_column(table, 'stale')
