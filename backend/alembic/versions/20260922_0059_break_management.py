"""break management

Revision ID: 20260922_0059
Revises: 20260921_0058
Create Date: 2026-09-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260922_0059'
down_revision = '20260921_0058'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'break_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reason', sa.String(length=120), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_break_sessions_user_id', 'break_sessions', ['user_id'], unique=False)
    op.create_index('ix_break_sessions_start_time', 'break_sessions', ['start_time'], unique=False)
    op.create_index('ix_break_sessions_end_time', 'break_sessions', ['end_time'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_break_sessions_end_time', table_name='break_sessions')
    op.drop_index('ix_break_sessions_start_time', table_name='break_sessions')
    op.drop_index('ix_break_sessions_user_id', table_name='break_sessions')
    op.drop_table('break_sessions')
