"""project.format — content intent / length selector (P3)

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-06-20 21:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b5c6d7e8f9a0'
down_revision: str | None = 'a4b5c6d7e8f9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'project', sa.Column('format', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('project', 'format')
