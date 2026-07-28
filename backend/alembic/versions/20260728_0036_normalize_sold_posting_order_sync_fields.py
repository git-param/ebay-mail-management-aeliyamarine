"""normalize sold posting order sync fields

Revision ID: 20260728_0036
Revises: 20260728_0035
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260728_0036'
down_revision = '20260728_0035'
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    columns = [column['name'] for column in inspect(op.get_bind()).get_columns(table_name)]
    return column_name in columns


def upgrade():
    for column_name in ['provider', 'first_synced_at', 'last_synced_at']:
        if _has_column('sold_posting_orders', column_name):
            op.drop_column('sold_posting_orders', column_name)
    op.execute(
        """
        UPDATE sold_posting_orders
        SET normalized_status = CASE
            WHEN cancel_state IN ('CANCELLED', 'CANCEL_REQUESTED', 'CANCEL_PENDING', 'CANCEL_IN_PROGRESS', 'CANCEL_COMPLETE', 'CANCEL_COMPLETED') THEN 'CANCELLED'::sold_posting_status
            WHEN order_fulfillment_status IN ('FULFILLED', 'SHIPPED') THEN 'SHIPPED'::sold_posting_status
            WHEN order_payment_status IN ('PAID', 'FULLY_PAID') AND order_fulfillment_status IN ('IN_PROGRESS', 'PARTIALLY_FULFILLED') THEN 'PARTIALLY_SHIPPED'::sold_posting_status
            WHEN order_payment_status IN ('PAID', 'FULLY_PAID') AND order_fulfillment_status IN ('NOT_STARTED', 'READY_FOR_SHIPMENT') THEN 'AWAITING_SHIPMENT'::sold_posting_status
            WHEN order_payment_status IN ('NOT_PAID', 'PENDING', 'FAILED') THEN 'AWAITING_PAYMENT'::sold_posting_status
            ELSE 'OTHER'::sold_posting_status
        END
        """
    )


def downgrade():
    if not _has_column('sold_posting_orders', 'provider'):
        op.add_column('sold_posting_orders', sa.Column('provider', sa.String(length=40), nullable=False, server_default='FULFILLMENT'))
        op.alter_column('sold_posting_orders', 'provider', server_default=None)
    if not _has_column('sold_posting_orders', 'first_synced_at'):
        op.add_column('sold_posting_orders', sa.Column('first_synced_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')))
        op.alter_column('sold_posting_orders', 'first_synced_at', server_default=None)
    if not _has_column('sold_posting_orders', 'last_synced_at'):
        op.add_column('sold_posting_orders', sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')))
        op.alter_column('sold_posting_orders', 'last_synced_at', server_default=None)
