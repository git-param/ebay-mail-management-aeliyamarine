import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class OfferStatus(str, enum.Enum):
    PENDING = 'PENDING'
    ACCEPTED = 'ACCEPTED'
    DECLINED = 'DECLINED'
    EXPIRED = 'EXPIRED'


class OfferDirection(str, enum.Enum):
    INCOMING = 'INCOMING'
    OUTGOING = 'OUTGOING'


class Offer(Base):
    __tablename__ = 'offers'
    __table_args__ = (UniqueConstraint('provider_offer_id', name='uq_offers_provider_offer_id'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_offer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey('conversations.id', ondelete='SET NULL'), nullable=True, index=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('ebay_accounts.id'), nullable=True, index=True)
    listing_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    buyer_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    offer_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[OfferStatus] = mapped_column(Enum(OfferStatus, name='offer_status'), nullable=False)
    direction: Mapped[OfferDirection] = mapped_column(Enum(OfferDirection, name='offer_direction'), nullable=False, default=OfferDirection.OUTGOING)
    offer_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quantity: Mapped[int] = mapped_column(default=1)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    conversation = relationship('Conversation', back_populates='offers')
