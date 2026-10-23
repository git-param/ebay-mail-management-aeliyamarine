"""Save dated employee work reports and their manual tasks."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20261023_0063'
down_revision = '20260930_0062'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'daily_work_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('report_date', sa.Date(), nullable=False),
        sa.Column('automatic_tasks', postgresql.JSONB(), nullable=False),
        sa.Column('additional_tasks', postgresql.JSONB(), nullable=False),
        sa.Column('report_text', sa.Text(), nullable=False),
        sa.Column('copied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('user_id', 'report_date', name='uq_daily_work_reports_user_date'),
    )
    op.create_index('ix_daily_work_reports_report_date', 'daily_work_reports', ['report_date'])


def downgrade() -> None:
    op.drop_index('ix_daily_work_reports_report_date', table_name='daily_work_reports')
    op.drop_table('daily_work_reports')
