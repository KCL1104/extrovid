"""shot framing + camera_id (ViMax adoption PR-A)

- shot.framing: blocking — subject frame positions, facing directions, focus
- shot.camera_id: physical camera setup index (shots sharing it = same setup)

Revision ID: a1f2c3d4e5b6
Revises: e9b3c5d7f1a4
Create Date: 2026-06-10 17:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a1f2c3d4e5b6'
down_revision: str | None = 'e9b3c5d7f1a4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'shot', sa.Column('framing', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.add_column(
        'shot',
        sa.Column('camera_id', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('shot', 'camera_id')
    op.drop_column('shot', 'framing')
