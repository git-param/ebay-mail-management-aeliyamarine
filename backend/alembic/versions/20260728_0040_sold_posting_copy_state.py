"""Add persistent copy state for sold posting line items.

Revision ID: 20260728_0040
Revises: 20260728_0039
Create Date: 2026-07-28 00:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260728_0040'
down_revision = '20260728_0039'
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column['name'] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column('sold_posting_line_items', 'copied_at'):
        op.add_column('sold_posting_line_items', sa.Column('copied_at', sa.DateTime(timezone=True), nullable=True))
    if not _has_column('sold_posting_line_items', 'copy_count'):
        op.add_column('sold_posting_line_items', sa.Column('copy_count', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    if _has_column('sold_posting_line_items', 'copy_count'):
        op.drop_column('sold_posting_line_items', 'copy_count')
    if _has_column('sold_posting_line_items', 'copied_at'):
        op.drop_column('sold_posting_line_items', 'copied_at')
