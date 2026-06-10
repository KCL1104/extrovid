"""brief.clarifications — persisted director Q&A (ViMax adoption PR-C)

Director Q&A answers become durable creative direction injected into every
downstream planning prompt instead of being consumed once by the BriefAgent.

Revision ID: b2c3d4e5f6a7
Revises: a1f2c3d4e5b6
Create Date: 2026-06-10 18:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1f2c3d4e5b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('brief', sa.Column('clarifications', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('brief', 'clarifications')
