"""sold posting delivered status

Revision ID: 20260728_0037
Revises: 20260728_0036
Create Date: 2026-07-28
"""

from alembic import op


revision = '20260728_0037'
down_revision = '20260728_0036'
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE sold_posting_status ADD VALUE IF NOT EXISTS 'DELIVERED'")
    op.execute(
        """
        UPDATE sold_posting_orders
        SET normalized_status = 'DELIVERED'::sold_posting_status
        WHERE raw_payload_json::text ILIKE '%DELIVERED%'
           OR raw_payload_json::text ILIKE '%actualDeliveryDate%'
           OR raw_payload_json::text ILIKE '%deliveredDate%'
        """
    )
    op.execute(
        """
        UPDATE sold_posting_orders
        SET normalized_status = 'CANCELLED'::sold_posting_status
        WHERE cancel_state IN (
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
        )
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE sold_posting_orders
        SET normalized_status = 'PAID_AND_SHIPPED'::sold_posting_status
        WHERE normalized_status::text = 'DELIVERED'
        """
    )
