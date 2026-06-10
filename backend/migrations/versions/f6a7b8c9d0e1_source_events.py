"""sourceevent — long-source import segmentation (ViMax PR-I)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-10 22:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: str | None = 'e5f6a7b8c9d0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'sourceevent',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), primary_key=True),
        sa.Column(
            'project_id',
            sqlmodel.sql.sqltypes.AutoString(),
            sa.ForeignKey('project.id'),
            nullable=False,
            index=True,
        ),
        sa.Column('index', sa.Integer(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('process_chain', sa.JSON(), nullable=True),
        sa.Column('is_last', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('sourceevent')
