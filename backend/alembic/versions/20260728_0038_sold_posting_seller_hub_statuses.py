"""sold posting seller hub statuses

Revision ID: 20260728_0038
Revises: 20260728_0037
Create Date: 2026-07-28
"""

from alembic import op


revision = '20260728_0038'
down_revision = '20260728_0037'
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        for value in [
            'AWAITING_SHIPMENT_OVERDUE',
            'AWAITING_SHIPMENT_WITHIN_24_HOURS',
            'AWAITING_EXPEDITED_SHIPMENT',
            'PAID_AND_SHIPPED',
            'PAID_AWAITING_FEEDBACK',
            'SHIPPED_AWAITING_FEEDBACK',
            'ARCHIVED',
        ]:
            op.execute(f"ALTER TYPE sold_posting_status ADD VALUE IF NOT EXISTS '{value}'")

    op.execute(
        """
        UPDATE sold_posting_orders
        SET normalized_status = CASE
            WHEN normalized_status::text IN ('PARTIALLY_REFUNDED') THEN 'REFUNDED'::sold_posting_status
            WHEN normalized_status::text IN ('PARTIALLY_SHIPPED', 'SHIPPED', 'DELIVERED') THEN 'PAID_AND_SHIPPED'::sold_posting_status
            WHEN cancel_state IN (
                'CANCELLED',
                'CANCELED',
                'CANCEL_REQUESTED',
                'CANCELLATION_REQUESTED',
                'CANCEL_PENDING',
                'CANCELLATION_PENDING',
                'CANCEL_IN_PROGRESS',
                'CANCELLATION_IN_PROGRESS',
                'CANCEL_COMPLETE',
                'CANCEL_COMPLETED',
                'CANCELLATION_COMPLETE',
                'CANCELLATION_COMPLETED'
            ) THEN 'CANCELLED'::sold_posting_status
            WHEN order_fulfillment_status IN ('FULFILLED', 'SHIPPED', 'FULLY_FULFILLED') THEN 'PAID_AND_SHIPPED'::sold_posting_status
            WHEN order_payment_status IN ('PAID', 'FULLY_PAID', 'PAID_IN_FULL') AND order_fulfillment_status IN ('IN_PROGRESS', 'PARTIALLY_FULFILLED', 'PARTIALLY_SHIPPED') THEN 'PAID_AND_SHIPPED'::sold_posting_status
            ELSE normalized_status
        END
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE sold_posting_orders
        SET normalized_status = CASE
            WHEN normalized_status::text IN ('PAID_AND_SHIPPED', 'PAID_AWAITING_FEEDBACK', 'SHIPPED_AWAITING_FEEDBACK', 'ARCHIVED') THEN 'SHIPPED'::sold_posting_status
            WHEN normalized_status::text IN ('AWAITING_SHIPMENT_OVERDUE', 'AWAITING_SHIPMENT_WITHIN_24_HOURS', 'AWAITING_EXPEDITED_SHIPMENT') THEN 'AWAITING_SHIPMENT'::sold_posting_status
            ELSE normalized_status
        END
        """
    )
