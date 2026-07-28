"""sold posting final statuses and condition

Revision ID: 20260728_0039
Revises: 20260728_0038
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = '20260728_0039'
down_revision = '20260728_0038'
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    return column_name in [column['name'] for column in inspect(op.get_bind()).get_columns(table_name)]


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE sold_posting_status ADD VALUE IF NOT EXISTS 'SHIPPED'")
        op.execute("ALTER TYPE sold_posting_status ADD VALUE IF NOT EXISTS 'DELIVERED'")

    if not _has_column('sold_posting_line_items', 'condition'):
        op.add_column('sold_posting_line_items', sa.Column('condition', sa.String(length=120), nullable=True))

    for table_name, column_name in [
        ('sold_posting_orders', 'tax_total'),
        ('sold_posting_line_items', 'legacy_variation_id'),
        ('sold_posting_line_items', 'shipping_cost'),
        ('sold_posting_line_items', 'variation_aspects_json'),
    ]:
        if _has_column(table_name, column_name):
            op.drop_column(table_name, column_name)

    op.execute(
        """
        UPDATE sold_posting_orders
        SET normalized_status = CASE
            WHEN normalized_status::text IN ('PARTIALLY_REFUNDED') THEN 'REFUNDED'::sold_posting_status
            WHEN normalized_status::text IN ('PARTIALLY_SHIPPED', 'PAID_AND_SHIPPED', 'PAID_AWAITING_FEEDBACK', 'SHIPPED_AWAITING_FEEDBACK', 'ARCHIVED') THEN 'SHIPPED'::sold_posting_status
            WHEN normalized_status::text IN ('AWAITING_SHIPMENT_OVERDUE', 'AWAITING_SHIPMENT_WITHIN_24_HOURS', 'AWAITING_EXPEDITED_SHIPMENT') THEN 'AWAITING_SHIPMENT'::sold_posting_status
            ELSE normalized_status
        END
        """
    )


def downgrade():
    if not _has_column('sold_posting_orders', 'tax_total'):
        op.add_column('sold_posting_orders', sa.Column('tax_total', sa.Numeric(14, 2), nullable=True))
    if not _has_column('sold_posting_line_items', 'legacy_variation_id'):
        op.add_column('sold_posting_line_items', sa.Column('legacy_variation_id', sa.String(length=255), nullable=True))
    if not _has_column('sold_posting_line_items', 'shipping_cost'):
        op.add_column('sold_posting_line_items', sa.Column('shipping_cost', sa.Numeric(14, 2), nullable=True))
    if not _has_column('sold_posting_line_items', 'variation_aspects_json'):
        op.add_column('sold_posting_line_items', sa.Column('variation_aspects_json', postgresql.JSONB(), nullable=True))
    if _has_column('sold_posting_line_items', 'condition'):
        op.drop_column('sold_posting_line_items', 'condition')
