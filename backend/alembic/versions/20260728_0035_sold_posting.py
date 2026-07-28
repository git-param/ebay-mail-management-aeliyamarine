"""sold posting

Revision ID: 20260728_0035
Revises: 20260727_0034
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260728_0035"
down_revision = "20260727_0034"
branch_labels = None
depends_on = None


sold_posting_status = postgresql.ENUM(
    "AWAITING_PAYMENT",
    "AWAITING_SHIPMENT",
    "PARTIALLY_SHIPPED",
    "SHIPPED",
    "CANCELLED",
    "REFUNDED",
    "PARTIALLY_REFUNDED",
    "OTHER",
    name="sold_posting_status",
    create_type=False,
)

sync_status = postgresql.ENUM(
    "IDLE",
    "RUNNING",
    "SUCCESS",
    "PARTIAL_FAILURE",
    "FAILED",
    name="sold_posting_sync_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    # Safely create PostgreSQL enum types only when they do not exist.
    sold_posting_status.create(bind, checkfirst=True)
    sync_status.create(bind, checkfirst=True)

    op.create_table(
        "sold_posting_orders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "ebay_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ebay_accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "ebay_account_name",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "legacy_order_id",
            sa.String(255),
        ),
        sa.Column(
            "sales_record_reference",
            sa.String(255),
        ),
        sa.Column(
            "seller_id",
            sa.String(255),
        ),
        sa.Column(
            "buyer_username",
            sa.String(255),
        ),
        sa.Column(
            "creation_date",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "last_modified_date",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "payment_date",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "order_payment_status",
            sa.String(100),
        ),
        sa.Column(
            "order_fulfillment_status",
            sa.String(100),
        ),
        sa.Column(
            "normalized_status",
            sold_posting_status,
            nullable=False,
        ),
        sa.Column(
            "cancel_state",
            sa.String(100),
        ),
        sa.Column(
            "currency",
            sa.String(10),
        ),
        sa.Column(
            "price_subtotal",
            sa.Numeric(14, 2),
        ),
        sa.Column(
            "delivery_cost",
            sa.Numeric(14, 2),
        ),
        sa.Column(
            "discount_total",
            sa.Numeric(14, 2),
        ),
        sa.Column(
            "tax_total",
            sa.Numeric(14, 2),
        ),
        sa.Column(
            "order_total",
            sa.Numeric(14, 2),
        ),
        sa.Column(
            "total_due_seller",
            sa.Numeric(14, 2),
        ),
        sa.Column(
            "total_marketplace_fee",
            sa.Numeric(14, 2),
        ),
        sa.Column(
            "listing_marketplace_ids",
            postgresql.JSONB,
        ),
        sa.Column(
            "purchase_marketplace_ids",
            postgresql.JSONB,
        ),
        sa.Column(
            "shipping_carrier_code",
            sa.String(120),
        ),
        sa.Column(
            "shipping_service_code",
            sa.String(120),
        ),
        sa.Column(
            "tracking_number",
            sa.String(255),
        ),
        sa.Column(
            "ship_by_date",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "min_estimated_delivery_date",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "max_estimated_delivery_date",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "raw_payload_json",
            postgresql.JSONB,
        ),
        sa.Column(
            "first_synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "ebay_account_id",
            "order_id",
            name="uq_sold_posting_orders_account_order",
        ),
    )

    for column in [
        "creation_date",
        "payment_date",
        "normalized_status",
        "ebay_account_id",
        "buyer_username",
        "order_id",
        "last_modified_date",
    ]:
        op.create_index(
            f"ix_sold_posting_orders_{column}",
            "sold_posting_orders",
            [column],
        )

    op.create_table(
        "sold_posting_line_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "sold_posting_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "sold_posting_orders.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "ebay_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ebay_accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "line_item_id",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "legacy_item_id",
            sa.String(255),
        ),
        sa.Column(
            "legacy_variation_id",
            sa.String(255),
        ),
        sa.Column(
            "sku",
            sa.String(255),
        ),
        sa.Column(
            "title",
            sa.String(500),
        ),
        sa.Column(
            "quantity",
            sa.Integer,
        ),
        sa.Column(
            "sold_format",
            sa.String(80),
        ),
        sa.Column(
            "line_item_fulfillment_status",
            sa.String(100),
        ),
        sa.Column(
            "listing_marketplace_id",
            sa.String(80),
        ),
        sa.Column(
            "purchase_marketplace_id",
            sa.String(80),
        ),
        sa.Column(
            "unit_price",
            sa.Numeric(14, 2),
        ),
        sa.Column(
            "line_item_cost",
            sa.Numeric(14, 2),
        ),
        sa.Column(
            "shipping_cost",
            sa.Numeric(14, 2),
        ),
        sa.Column(
            "discount_amount",
            sa.Numeric(14, 2),
        ),
        sa.Column(
            "line_item_total",
            sa.Numeric(14, 2),
        ),
        sa.Column(
            "currency",
            sa.String(10),
        ),
        sa.Column(
            "ship_by_date",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "image_url",
            sa.Text,
        ),
        sa.Column(
            "variation_aspects_json",
            postgresql.JSONB,
        ),
        sa.Column(
            "raw_payload_json",
            postgresql.JSONB,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "ebay_account_id",
            "order_id",
            "line_item_id",
            name="uq_sold_posting_line_items_account_order_line",
        ),
    )

    for column in [
        "ebay_account_id",
        "sku",
        "legacy_item_id",
        "order_id",
    ]:
        op.create_index(
            f"ix_sold_posting_line_items_{column}",
            "sold_posting_line_items",
            [column],
        )

    op.create_table(
        "sold_posting_sync_states",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "ebay_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ebay_accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "initial_sync_completed",
            sa.Boolean,
            nullable=False,
        ),
        sa.Column(
            "last_successful_sync_at",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "last_attempted_sync_at",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "sync_status",
            sync_status,
            nullable=False,
        ),
        sa.Column(
            "pages_fetched",
            sa.Integer,
            nullable=False,
        ),
        sa.Column(
            "orders_received",
            sa.Integer,
            nullable=False,
        ),
        sa.Column(
            "orders_inserted",
            sa.Integer,
            nullable=False,
        ),
        sa.Column(
            "orders_updated",
            sa.Integer,
            nullable=False,
        ),
        sa.Column(
            "line_items_inserted",
            sa.Integer,
            nullable=False,
        ),
        sa.Column(
            "error_message",
            sa.Text,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "ebay_account_id",
            name="uq_sold_posting_sync_states_account",
        ),
    )

    op.create_index(
        "ix_sold_posting_sync_states_ebay_account_id",
        "sold_posting_sync_states",
        ["ebay_account_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index(
        "ix_sold_posting_sync_states_ebay_account_id",
        table_name="sold_posting_sync_states",
    )
    op.drop_table("sold_posting_sync_states")

    op.drop_table("sold_posting_line_items")
    op.drop_table("sold_posting_orders")

    sync_status.drop(bind, checkfirst=True)
    sold_posting_status.drop(bind, checkfirst=True)