"""per-shot detailed direction

- shot.extra_direction: free-text director notes, fed verbatim into the generation prompt
- shot.character_id: cast lock — FK to characterprofile, the shot's default character

Revision ID: e9b3c5d7f1a4
Revises: d4e8f1a2b3c6
Create Date: 2026-06-10 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e9b3c5d7f1a4'
down_revision: str | None = 'd4e8f1a2b3c6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'shot', sa.Column('extra_direction', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.add_column(
        'shot',
        sa.Column(
            'character_id',
            sqlmodel.sql.sqltypes.AutoString(),
            sa.ForeignKey('characterprofile.id'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('shot', 'character_id')
    op.drop_column('shot', 'extra_direction')
