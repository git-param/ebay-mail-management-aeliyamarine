import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class EbayOrder(Base):
    __tablename__ = 'orders'
    __table_args__ = (UniqueConstraint('account_id', 'order_id', name='uq_orders_account_order_id'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('ebay_accounts.id'), nullable=False)
    order_id: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fulfillment_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cancel_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    refund_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    pricing_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    refunds: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    external_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_last_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    line_items = relationship(
        'EbayOrderLineItem',
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='EbayOrderLineItem.created_at',
    )
    returns = relationship(
        'EbayReturn',
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='EbayReturn.created_at',
    )
    cancellations = relationship(
        'EbayCancellation',
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='EbayCancellation.created_at',
    )


class EbayOrderLineItem(Base):
    __tablename__ = 'order_line_items'
    __table_args__ = (UniqueConstraint('account_id', 'order_id', 'line_item_id', name='uq_order_line_items_account_order_line'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('ebay_accounts.id'), nullable=False)
    order_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    order_id: Mapped[str] = mapped_column(String(255), nullable=False)
    line_item_id: Mapped[str] = mapped_column(String(255), nullable=False)
    item_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    listing_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    order = relationship('EbayOrder', back_populates='line_items')


class ConversationOrderContext(Base):
    __tablename__ = 'conversation_order_contexts'
    __table_args__ = (UniqueConstraint('conversation_id', name='uq_conversation_order_contexts_conversation'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    order_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('orders.id', ondelete='SET NULL'), nullable=True)
    ebay_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legacy_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ebay_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    listing_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    buyer_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inventory_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_strategy: Mapped[str] = mapped_column(String(80), nullable=False, default='NO_MATCH')
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_identifiers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sync_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    conversation = relationship('Conversation', back_populates='order_mapping')
    order = relationship('EbayOrder')


class ConversationProductContext(Base):
    __tablename__ = 'conversation_product_contexts'
    __table_args__ = (UniqueConstraint('conversation_id', name='uq_conversation_product_contexts_conversation'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(50), nullable=False)
    item_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    seller_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enrichment_status: Mapped[str] = mapped_column(String(50), nullable=False, default='PENDING')
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    conversation = relationship('Conversation', back_populates='product_context')


class EbayReturn(Base):
    __tablename__ = 'returns'
    __table_args__ = (UniqueConstraint('account_id', 'return_id', name='uq_returns_account_return_id'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('ebay_accounts.id'), nullable=False)
    order_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('orders.id', ondelete='SET NULL'), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    return_id: Mapped[str] = mapped_column(String(255), nullable=False)
    return_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    return_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    return_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    order = relationship('EbayOrder', back_populates='returns')


class EbayCancellation(Base):
    __tablename__ = 'cancellations'
    __table_args__ = (UniqueConstraint('account_id', 'cancel_id', name='uq_cancellations_account_cancel_id'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('ebay_accounts.id'), nullable=False)
    order_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('orders.id', ondelete='SET NULL'), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    cancel_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requester: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    order = relationship('EbayOrder', back_populates='cancellations')
