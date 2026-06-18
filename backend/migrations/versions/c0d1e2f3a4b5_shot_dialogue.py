"""shot.dialogue + shot.speaker — per-shot spoken line binding

The one spoken line delivered in a shot and who says it ('narrator' for voiceover) —
drives captions, the performance prompt, and TTS voiceover.

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-06-18 14:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c0d1e2f3a4b5'
down_revision: str | None = 'b9c0d1e2f3a4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('shot', sa.Column('dialogue', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('shot', sa.Column('speaker', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column('shot', 'speaker')
    op.drop_column('shot', 'dialogue')
