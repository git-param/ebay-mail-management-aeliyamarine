# app/models/offer.py

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class OfferStatus:
    """Offer status constants"""
    PENDING = 'PENDING'
    ACCEPTED = 'ACCEPTED'
    DECLINED = 'DECLINED'
    EXPIRED = 'EXPIRED'
    COUNTERED = 'COUNTERED'
    RETRACTED = 'RETRACTED'


class OfferDirection:
    """Offer direction constants"""
    INCOMING = 'INCOMING'  # Buyer sent offer to seller
    OUTGOING = 'OUTGOING'  # Seller sent offer to buyer


class Offer(Base):
    __tablename__ = 'offers'
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('ebay_accounts.id'), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=True)
    
    provider_offer_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    listing_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    buyer_username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    
    offer_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default='USD')
    status: Mapped[str] = mapped_column(String(50), default=OfferStatus.PENDING)
    direction: Mapped[str] = mapped_column(String(50), nullable=False)
    offer_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=datetime.utcnow)
    
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    # Relationships
    account: Mapped["EbayAccount"] = relationship(
        "EbayAccount",
        back_populates="offers"
    )
    conversation: Mapped["Conversation | None"] = relationship(
        "Conversation",
        back_populates="offers"
    )
    
    def __repr__(self):
        return f"<Offer {self.provider_offer_id} {self.status} ${self.offer_amount}>"