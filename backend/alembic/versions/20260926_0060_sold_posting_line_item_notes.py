"""Add notes to sold posting line items.

Revision ID: 20260926_0060
Revises: 20260922_0059
Create Date: 2026-09-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260926_0060'
down_revision = '20260922_0059'
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column['name'] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column('sold_posting_line_items', 'note'):
        op.add_column('sold_posting_line_items', sa.Column('note', sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column('sold_posting_line_items', 'note'):
        op.drop_column('sold_posting_line_items', 'note')
