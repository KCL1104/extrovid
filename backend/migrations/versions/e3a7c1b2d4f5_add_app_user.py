"""add app_user

Revision ID: e3a7c1b2d4f5
Revises: fdfb08911737
Create Date: 2026-06-01 20:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e3a7c1b2d4f5'
down_revision: str | None = 'fdfb08911737'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('app_user',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('password_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('google_sub', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('daily_video_cap', sa.Integer(), nullable=False),
    sa.Column('daily_image_cap', sa.Integer(), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_app_user_email'), 'app_user', ['email'], unique=True)
    op.create_index(op.f('ix_app_user_google_sub'), 'app_user', ['google_sub'], unique=True)
    op.create_index(op.f('ix_app_user_token_hash'), 'app_user', ['token_hash'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_app_user_token_hash'), table_name='app_user')
    op.drop_index(op.f('ix_app_user_google_sub'), table_name='app_user')
    op.drop_index(op.f('ix_app_user_email'), table_name='app_user')
    op.drop_table('app_user')
