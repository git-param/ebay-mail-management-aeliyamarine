"""leave management

Revision ID: 20260820_0046
Revises: 20260811_0045
Create Date: 2026-08-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260820_0046'
down_revision = '87d5266f6b0c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'leave_policies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('paid_leave_per_month', sa.Numeric(5, 2), nullable=False, server_default='1.5'),
        sa.Column('instance_limit', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('short_leave_limit', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('instance_max_minutes', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('short_leave_max_minutes', sa.Integer(), nullable=False, server_default='120'),
        sa.Column('office_start_time', sa.Time(), nullable=False, server_default='10:00:00'),
        sa.Column('office_end_time', sa.Time(), nullable=False, server_default='19:00:00'),
        sa.Column('break_start_time', sa.Time(), nullable=True),
        sa.Column('break_end_time', sa.Time(), nullable=True),
        sa.Column('attendance_deduction_per_excess', sa.Numeric(5, 2), nullable=False, server_default='1'),
        sa.Column('punctuality_deduction_per_extra_instance', sa.Numeric(5, 2), nullable=False, server_default='1'),
        sa.Column('short_leave_over_limit_action', sa.String(20), nullable=False, server_default='BLOCK'),
        sa.Column('effective_from', sa.Date(), nullable=False, server_default='2026-08-01'),
        sa.Column('updated_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    op.create_table(
        'leave_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('leave_type', sa.String(30), nullable=False),
        sa.Column('day_part', sa.String(20), nullable=True),
        sa.Column('instance_kind', sa.String(20), nullable=True),
        sa.Column('short_leave_pattern', sa.String(30), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=True),
        sa.Column('end_time', sa.Time(), nullable=True),
        sa.Column('duration_days', sa.Numeric(6, 2), nullable=False, server_default='0'),
        sa.Column('duration_minutes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('paid_days', sa.Numeric(6, 2), nullable=False, server_default='0'),
        sa.Column('excess_days', sa.Numeric(6, 2), nullable=False, server_default='0'),
        sa.Column('pms_attendance_deduction', sa.Numeric(6, 2), nullable=False, server_default='0'),
        sa.Column('pms_punctuality_deduction', sa.Numeric(6, 2), nullable=False, server_default='0'),
        sa.Column('reviewed_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_leave_requests_user_month', 'leave_requests', ['user_id', 'start_date'])
    op.create_index('ix_leave_requests_status', 'leave_requests', ['status'])

    op.create_table(
        'leave_balance_ledger',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('entry_type', sa.String(30), nullable=False),
        sa.Column('amount', sa.Numeric(6, 2), nullable=False),
        sa.Column('source_request_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('leave_requests.id'), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('source_request_id', 'entry_type', name='uq_leave_ledger_request_entry_type'),
    )
    op.create_index('ix_leave_ledger_user_month', 'leave_balance_ledger', ['user_id', 'year', 'month'])

    op.execute(
        """
        INSERT INTO leave_policies (
            id, paid_leave_per_month, instance_limit, short_leave_limit,
            instance_max_minutes, short_leave_max_minutes, office_start_time,
            office_end_time, attendance_deduction_per_excess,
            punctuality_deduction_per_extra_instance, short_leave_over_limit_action,
            effective_from, created_at, updated_at
        )
        VALUES (
            gen_random_uuid(), 1.5, 3, 1, 30, 120, '10:00:00',
            '19:00:00', 1, 1, 'BLOCK', '2026-08-01', now(), now()
        )
        """
    )


def downgrade() -> None:
    op.drop_index('ix_leave_ledger_user_month', table_name='leave_balance_ledger')
    op.drop_table('leave_balance_ledger')
    op.drop_index('ix_leave_requests_status', table_name='leave_requests')
    op.drop_index('ix_leave_requests_user_month', table_name='leave_requests')
    op.drop_table('leave_requests')
    op.drop_table('leave_policies')
