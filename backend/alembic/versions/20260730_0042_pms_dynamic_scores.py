"""pms dynamic scores and audit history

Revision ID: 20260730_0042
Revises: 20260730_0041
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260730_0042'
down_revision = '20260730_0041'
branch_labels = None
depends_on = None


def upgrade() -> None:
    error_level = postgresql.ENUM('NO_ERROR', 'MINOR', 'MAJOR', name='pms_error_level')
    error_level.create(op.get_bind(), checkfirst=True)
    op.add_column('pms_daily_task_entries', sa.Column('score_items', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('pms_daily_task_entries', sa.Column('error_level', error_level, nullable=False, server_default='NO_ERROR'))
    op.add_column('pms_daily_task_entries', sa.Column('error_remark', sa.Text(), nullable=True))
    op.add_column('pms_daily_task_entries', sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('pms_daily_task_entries', sa.Column('updated_by_user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_pms_daily_task_entries_created_by_user_id_users', 'pms_daily_task_entries', 'users', ['created_by_user_id'], ['id'])
    op.create_foreign_key('fk_pms_daily_task_entries_updated_by_user_id_users', 'pms_daily_task_entries', 'users', ['updated_by_user_id'], ['id'])
    op.create_table(
        'pms_daily_task_entry_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entry_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('changed_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(length=40), nullable=False),
        sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['entry_id'], ['pms_daily_task_entries.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pms_daily_task_entry_history_entry_id', 'pms_daily_task_entry_history', ['entry_id'])


def downgrade() -> None:
    op.drop_index('ix_pms_daily_task_entry_history_entry_id', table_name='pms_daily_task_entry_history')
    op.drop_table('pms_daily_task_entry_history')
    op.drop_constraint('fk_pms_daily_task_entries_updated_by_user_id_users', 'pms_daily_task_entries', type_='foreignkey')
    op.drop_constraint('fk_pms_daily_task_entries_created_by_user_id_users', 'pms_daily_task_entries', type_='foreignkey')
    op.drop_column('pms_daily_task_entries', 'updated_by_user_id')
    op.drop_column('pms_daily_task_entries', 'created_by_user_id')
    op.drop_column('pms_daily_task_entries', 'error_remark')
    op.drop_column('pms_daily_task_entries', 'error_level')
    op.drop_column('pms_daily_task_entries', 'score_items')
    postgresql.ENUM(name='pms_error_level').drop(op.get_bind(), checkfirst=True)
