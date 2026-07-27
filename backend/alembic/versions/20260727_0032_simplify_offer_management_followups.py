"""simplify offer management followups

Revision ID: 20260727_0032
Revises: 20260727_0031
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = '20260727_0032'
down_revision = '20260727_0031'
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return column_name in [column['name'] for column in inspector.get_columns(table_name)]


def upgrade() -> None:
    for column_name in [
        'follow_up_1_date',
        'follow_up_1_status',
        'follow_up_1_completed_at',
        'follow_up_2_date',
        'follow_up_2_status',
        'follow_up_2_completed_at',
        'internal_notes',
    ]:
        if _has_column('offer_management_entries', column_name):
            op.drop_column('offer_management_entries', column_name)

    op.execute('DROP TYPE IF EXISTS offer_management_follow_up_status')


def downgrade() -> None:
    follow_up_enum = postgresql.ENUM(
        'NOT_SCHEDULED',
        'SCHEDULED',
        'COMPLETED',
        'SKIPPED',
        'NOT_REQUIRED',
        name='offer_management_follow_up_status',
    )
    follow_up_enum.create(op.get_bind(), checkfirst=True)

    if not _has_column('offer_management_entries', 'follow_up_1_date'):
        op.add_column('offer_management_entries', sa.Column('follow_up_1_date', sa.Date(), nullable=True))
    if not _has_column('offer_management_entries', 'follow_up_1_status'):
        op.add_column('offer_management_entries', sa.Column('follow_up_1_status', follow_up_enum, nullable=False, server_default='NOT_SCHEDULED'))
    if not _has_column('offer_management_entries', 'follow_up_1_completed_at'):
        op.add_column('offer_management_entries', sa.Column('follow_up_1_completed_at', sa.DateTime(timezone=True), nullable=True))
    if not _has_column('offer_management_entries', 'follow_up_2_date'):
        op.add_column('offer_management_entries', sa.Column('follow_up_2_date', sa.Date(), nullable=True))
    if not _has_column('offer_management_entries', 'follow_up_2_status'):
        op.add_column('offer_management_entries', sa.Column('follow_up_2_status', follow_up_enum, nullable=False, server_default='NOT_SCHEDULED'))
    if not _has_column('offer_management_entries', 'follow_up_2_completed_at'):
        op.add_column('offer_management_entries', sa.Column('follow_up_2_completed_at', sa.DateTime(timezone=True), nullable=True))
    if not _has_column('offer_management_entries', 'internal_notes'):
        op.add_column('offer_management_entries', sa.Column('internal_notes', sa.Text(), nullable=True))
