"""add sub-subtasks for task management

Revision ID: 20260821_0048
Revises: 39f78ec06804
Create Date: 2026-08-21 00:48:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260821_0048'
down_revision = '39f78ec06804'
branch_labels = None
depends_on = None


task_status = postgresql.ENUM('ACTIVE', 'INACTIVE', 'ARCHIVED', name='task_status', create_type=False)
source_type = postgresql.ENUM(
    'MESSAGE_CATEGORY',
    'CONVERSATION_CATEGORY',
    'SOLD_POSTING',
    'PRICING_UPDATE',
    'QUANTITY_SYNC',
    'BOOKING',
    'INVOICE',
    'TRACKING',
    'PURCHASE',
    'MANUAL',
    'CUSTOM',
    'MESSAGE_TYPE',
    'OFFER_MANAGEMENT',
    'OTHER_GENERAL_WORK',
    name='subtask_source_type',
    create_type=False,
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE subtask_source_type ADD VALUE IF NOT EXISTS 'OFFER_MANAGEMENT'")
        op.execute("ALTER TYPE subtask_source_type ADD VALUE IF NOT EXISTS 'OTHER_GENERAL_WORK'")

    op.create_table(
        'sub_subtasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('subtask_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('subtasks.id', ondelete='CASCADE'), nullable=False),
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
    op.create_index('ix_sub_subtasks_subtask_id', 'sub_subtasks', ['subtask_id'])
    op.create_index('ix_sub_subtasks_subtask_order', 'sub_subtasks', ['subtask_id', 'display_order'])
    op.create_index('ix_sub_subtasks_source_type', 'sub_subtasks', ['source_type'])

    op.add_column('user_subtask_assignments', sa.Column('sub_subtask_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_user_subtask_assignments_sub_subtask_id',
        'user_subtask_assignments',
        'sub_subtasks',
        ['sub_subtask_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.create_index('ix_user_subtask_assignments_sub_subtask_id', 'user_subtask_assignments', ['sub_subtask_id'])
    op.drop_constraint('uq_user_subtask_assignment_effective_from', 'user_subtask_assignments', type_='unique')
    op.create_unique_constraint(
        'uq_user_subtask_assignment_effective_from',
        'user_subtask_assignments',
        ['user_id', 'subtask_id', 'sub_subtask_id', 'effective_from'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_user_subtask_assignment_effective_from', 'user_subtask_assignments', type_='unique')
    op.create_unique_constraint(
        'uq_user_subtask_assignment_effective_from',
        'user_subtask_assignments',
        ['user_id', 'subtask_id', 'effective_from'],
    )
    op.drop_index('ix_user_subtask_assignments_sub_subtask_id', table_name='user_subtask_assignments')
    op.drop_constraint('fk_user_subtask_assignments_sub_subtask_id', 'user_subtask_assignments', type_='foreignkey')
    op.drop_column('user_subtask_assignments', 'sub_subtask_id')

    op.drop_index('ix_sub_subtasks_source_type', table_name='sub_subtasks')
    op.drop_index('ix_sub_subtasks_subtask_order', table_name='sub_subtasks')
    op.drop_index('ix_sub_subtasks_subtask_id', table_name='sub_subtasks')
    op.drop_table('sub_subtasks')
