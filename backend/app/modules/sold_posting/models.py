import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class SoldPostingStatus(str, enum.Enum):
    AWAITING_PAYMENT = 'AWAITING_PAYMENT'
    AWAITING_SHIPMENT = 'AWAITING_SHIPMENT'
    PARTIALLY_SHIPPED = 'PARTIALLY_SHIPPED'
    SHIPPED = 'SHIPPED'
    CANCELLED = 'CANCELLED'
    REFUNDED = 'REFUNDED'
    PARTIALLY_REFUNDED = 'PARTIALLY_REFUNDED'
    OTHER = 'OTHER'


class SoldPostingSyncStatus(str, enum.Enum):
    IDLE = 'IDLE'
    RUNNING = 'RUNNING'
    SUCCESS = 'SUCCESS'
    PARTIAL_FAILURE = 'PARTIAL_FAILURE'
    FAILED = 'FAILED'


class SoldPostingOrder(Base):
    __tablename__ = 'sold_posting_orders'
    __table_args__ = (
        UniqueConstraint('ebay_account_id', 'order_id', name='uq_sold_posting_orders_account_order'),
        Index('ix_sold_posting_orders_creation_date', 'creation_date'),
        Index('ix_sold_posting_orders_payment_date', 'payment_date'),
        Index('ix_sold_posting_orders_normalized_status', 'normalized_status'),
        Index('ix_sold_posting_orders_ebay_account_id', 'ebay_account_id'),
        Index('ix_sold_posting_orders_buyer_username', 'buyer_username'),
        Index('ix_sold_posting_orders_order_id', 'order_id'),
        Index('ix_sold_posting_orders_last_modified_date', 'last_modified_date'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ebay_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('ebay_accounts.id'), nullable=False)
    ebay_account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default='FULFILLMENT')
    order_id: Mapped[str] = mapped_column(String(255), nullable=False)
    legacy_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sales_record_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seller_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    buyer_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creation_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_modified_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_payment_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    order_fulfillment_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    normalized_status: Mapped[SoldPostingStatus] = mapped_column(Enum(SoldPostingStatus, name='sold_posting_status'), nullable=False, default=SoldPostingStatus.OTHER)
    cancel_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    price_subtotal: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    delivery_cost: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    discount_total: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    tax_total: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    order_total: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_due_seller: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_marketplace_fee: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    listing_marketplace_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    purchase_marketplace_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    shipping_carrier_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    shipping_service_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ship_by_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    min_estimated_delivery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_estimated_delivery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    first_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    account = relationship('EbayAccount')
    line_items = relationship('SoldPostingLineItem', back_populates='order', cascade='all, delete-orphan')


class SoldPostingLineItem(Base):
    __tablename__ = 'sold_posting_line_items'
    __table_args__ = (
        UniqueConstraint('ebay_account_id', 'order_id', 'line_item_id', name='uq_sold_posting_line_items_account_order_line'),
        Index('ix_sold_posting_line_items_ebay_account_id', 'ebay_account_id'),
        Index('ix_sold_posting_line_items_sku', 'sku'),
        Index('ix_sold_posting_line_items_legacy_item_id', 'legacy_item_id'),
        Index('ix_sold_posting_line_items_order_id', 'order_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sold_posting_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('sold_posting_orders.id', ondelete='CASCADE'), nullable=False)
    ebay_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('ebay_accounts.id'), nullable=False)
    order_id: Mapped[str] = mapped_column(String(255), nullable=False)
    line_item_id: Mapped[str] = mapped_column(String(255), nullable=False)
    legacy_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legacy_variation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sold_format: Mapped[str | None] = mapped_column(String(80), nullable=True)
    line_item_fulfillment_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    listing_marketplace_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    purchase_marketplace_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    line_item_cost: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    shipping_cost: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    discount_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    line_item_total: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ship_by_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    variation_aspects_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    raw_payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    order = relationship('SoldPostingOrder', back_populates='line_items')


class SoldPostingSyncState(Base):
    __tablename__ = 'sold_posting_sync_states'
    __table_args__ = (
        UniqueConstraint('ebay_account_id', name='uq_sold_posting_sync_states_account'),
        Index('ix_sold_posting_sync_states_ebay_account_id', 'ebay_account_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ebay_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('ebay_accounts.id'), nullable=False)
    initial_sync_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempted_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[SoldPostingSyncStatus] = mapped_column(Enum(SoldPostingSyncStatus, name='sold_posting_sync_status'), nullable=False, default=SoldPostingSyncStatus.IDLE)
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    line_items_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    account = relationship('EbayAccount')
