import enum
import uuid
from datetime import UTC, datetime, date
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class OfferManagementStatus(str, enum.Enum):
    OPEN = 'OPEN'
    CLOSED = 'CLOSED'
    NEW = 'NEW'
    REVIEWING = 'REVIEWING'
    COUNTEROFFER_SENT = 'COUNTEROFFER_SENT'
    AWAITING_BUYER = 'AWAITING_BUYER'
    FOLLOW_UP_DUE = 'FOLLOW_UP_DUE'
    AWAITING_PAYMENT = 'AWAITING_PAYMENT'
    SOLD = 'SOLD'
    CLOSED_PRICE_NOT_MATCHED = 'CLOSED_PRICE_NOT_MATCHED'
    CLOSED_NO_RESPONSE = 'CLOSED_NO_RESPONSE'
    CLOSED_BUYER_PURCHASED_ELSEWHERE = 'CLOSED_BUYER_PURCHASED_ELSEWHERE'
    CLOSED_OUT_OF_STOCK = 'CLOSED_OUT_OF_STOCK'
    CANCELLED = 'CANCELLED'


class OfferManagementOutcome(str, enum.Enum):
    PENDING = 'PENDING'
    DONE = 'DONE'
    IGNORE = 'IGNORE'
    SOLD = 'SOLD'
    NOT_ABLE_TO_MATCH_THE_PRICE = 'NOT_ABLE_TO_MATCH_THE_PRICE'
    CONVERTED_TO_SALE = 'CONVERTED_TO_SALE'
    BUYER_REJECTED = 'BUYER_REJECTED'
    SELLER_REJECTED = 'SELLER_REJECTED'
    NO_RESPONSE = 'NO_RESPONSE'
    PRICE_NOT_MATCHED = 'PRICE_NOT_MATCHED'
    BUYER_PURCHASED_ELSEWHERE = 'BUYER_PURCHASED_ELSEWHERE'
    OUT_OF_STOCK = 'OUT_OF_STOCK'
    M2M = 'M2M'
    OTHER = 'OTHER'


class OfferManagementEntry(Base):
    __tablename__ = 'offer_management_entries'
    __table_args__ = (
        Index('ix_offer_management_entries_listing_id', 'listing_id'),
        Index('ix_offer_management_entries_sku', 'sku'),
        Index('ix_offer_management_entries_buyer_id', 'buyer_id'),
        Index('ix_offer_management_entries_created_by_user_id', 'created_by_user_id'),
        Index('ix_offer_management_entries_offer_date', 'offer_date'),
        Index('ix_offer_management_entries_status', 'status'),
        Index('ix_offer_management_entries_ebay_account_id', 'ebay_account_id'),
        Index('ix_offer_management_entries_created_at', 'created_at'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    offer_date: Mapped[date] = mapped_column(Date, nullable=False)
    ebay_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('ebay_accounts.id'), nullable=False)
    ebay_account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    listing_id: Mapped[str] = mapped_column(String(32), nullable=False)
    listing_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    listing_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offer_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default='USD')
    listed_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    revised_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    automated_offer_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    buyer_offer_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    offered_price: Mapped[str | None] = mapped_column(String(255), nullable=True)
    buyer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[OfferManagementStatus] = mapped_column(Enum(OfferManagementStatus, name='offer_management_status'), nullable=False, default=OfferManagementStatus.OPEN)
    outcome: Mapped[OfferManagementOutcome] = mapped_column(Enum(OfferManagementOutcome, name='offer_management_outcome'), nullable=False, default=OfferManagementOutcome.PENDING)
    is_high_value: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_vip_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    next_offer_followup: Mapped[date | None] = mapped_column(Date, nullable=True)
    follow_up_1_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_2_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=True)
    related_offer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('offers.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    created_by = relationship('User', foreign_keys=[created_by_user_id])
    updated_by = relationship('User', foreign_keys=[updated_by_user_id])
    ebay_account = relationship('EbayAccount')
    related_conversation = relationship('Conversation')
    related_offer = relationship('Offer')


class OfferManagementEntryHistory(Base):
    __tablename__ = 'offer_management_entry_history'
    __table_args__ = (
        Index('ix_offer_management_entry_history_entry_id', 'offer_entry_id'),
        Index('ix_offer_management_entry_history_changed_by_user_id', 'changed_by_user_id'),
        Index('ix_offer_management_entry_history_changed_at', 'changed_at'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    offer_entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('offer_management_entries.id', ondelete='CASCADE'), nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    previous_values: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    entry = relationship('OfferManagementEntry')
    changed_by = relationship('User')
