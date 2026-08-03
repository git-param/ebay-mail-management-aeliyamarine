"""task management foundation

Revision ID: 20260803_0100
Revises: f3d5c50fa008
Create Date: 2026-08-03 00:10:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260803_0100'
down_revision = 'f3d5c50fa008'
branch_labels = None
depends_on = None


task_status = postgresql.ENUM('ACTIVE', 'INACTIVE', 'ARCHIVED', name='task_status', create_type=False)
source_type = postgresql.ENUM('MESSAGE_CATEGORY', 'CONVERSATION_CATEGORY', 'SOLD_POSTING', 'PRICING_UPDATE', 'QUANTITY_SYNC', 'BOOKING', 'INVOICE', 'TRACKING', 'PURCHASE', 'MANUAL', 'CUSTOM', name='subtask_source_type', create_type=False)
target_type = postgresql.ENUM('ANY_ACTIVITY', 'FIXED_COUNT', 'COMPLETION_PERCENTAGE', 'MANUAL', name='assignment_target_type', create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    task_status.create(bind, checkfirst=True)
    source_type.create(bind, checkfirst=True)
    target_type.create(bind, checkfirst=True)

    op.create_table(
        'task_categories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', task_status, nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_task_categories_status_order', 'task_categories', ['status', 'display_order'])

    op.create_table(
        'subtasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('task_category_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('task_categories.id'), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', task_status, nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source_type', source_type, nullable=False),
        sa.Column('source_reference_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_configuration', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('count_method', sa.String(length=80), nullable=True),
        sa.Column('completion_rule', sa.String(length=80), nullable=True),
        sa.Column('supports_automatic_fetch', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_subtasks_task_category_id', 'subtasks', ['task_category_id'])
    op.create_index('ix_subtasks_category_order', 'subtasks', ['task_category_id', 'display_order'])
    op.create_index('ix_subtasks_source_type', 'subtasks', ['source_type'])

    op.create_table(
        'user_subtask_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('subtask_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('subtasks.id'), nullable=False),
        sa.Column('quality_weight', sa.Numeric(6, 2), nullable=False, server_default='0'),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('auto_fetch_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('target_type', target_type, nullable=False),
        sa.Column('target_value', sa.Integer(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', task_status, nullable=False),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('user_id', 'subtask_id', 'effective_from', name='uq_user_subtask_assignment_effective_from'),
    )
    op.create_index('ix_user_subtask_assignments_user_id', 'user_subtask_assignments', ['user_id'])
    op.create_index('ix_user_subtask_assignments_subtask_id', 'user_subtask_assignments', ['subtask_id'])
    op.create_index('ix_user_subtask_assignments_user_dates', 'user_subtask_assignments', ['user_id', 'effective_from', 'effective_to'])


def downgrade() -> None:
    op.drop_index('ix_user_subtask_assignments_user_dates', table_name='user_subtask_assignments')
    op.drop_index('ix_user_subtask_assignments_subtask_id', table_name='user_subtask_assignments')
    op.drop_index('ix_user_subtask_assignments_user_id', table_name='user_subtask_assignments')
    op.drop_table('user_subtask_assignments')
    op.drop_index('ix_subtasks_source_type', table_name='subtasks')
    op.drop_index('ix_subtasks_category_order', table_name='subtasks')
    op.drop_index('ix_subtasks_task_category_id', table_name='subtasks')
    op.drop_table('subtasks')
    op.drop_index('ix_task_categories_status_order', table_name='task_categories')
    op.drop_table('task_categories')
    target_type.drop(op.get_bind(), checkfirst=True)
    source_type.drop(op.get_bind(), checkfirst=True)
    task_status.drop(op.get_bind(), checkfirst=True)
