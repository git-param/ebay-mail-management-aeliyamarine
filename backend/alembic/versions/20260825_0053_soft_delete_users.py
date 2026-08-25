"""soft delete users

Revision ID: 20260825_0053
Revises: 20260825_0052
Create Date: 2026-08-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260825_0053'
down_revision = '20260825_0052'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('deleted_by_user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index('ix_users_deleted_at', 'users', ['deleted_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_users_deleted_at', table_name='users')
    op.drop_column('users', 'deleted_by_user_id')
    op.drop_column('users', 'deleted_at')
