# app/models/offer.py

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, text, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class OfferStatus:
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    COUNTERED = "COUNTERED"
    RETRACTED = "RETRACTED"


class OfferDirection:
    INCOMING = "INCOMING"
    OUTGOING = "OUTGOING"


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (
        Index('ix_offers_current_account_status_expiry', 'account_id', 'provider_status', 'expires_at'),
        Index('ix_offers_reconciliation', 'account_id', 'reconciliation_required', 'last_synced_at'),
        UniqueConstraint(
            "provider",
            "account_id",
            "provider_offer_id",
            name="uq_offers_provider_account_offer_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="EBAY")
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ebay_accounts.id"), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True)

    provider_offer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    listing_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    buyer_username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    offer_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=OfferStatus.PENDING)
    direction: Mapped[str] = mapped_column(String(50), nullable=False)
    offer_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Trading evidence is separate from legacy conversation parsing/timeline data.
    record_source: Mapped[str] = mapped_column(String(32), default="LEGACY_UNKNOWN", server_default="LEGACY_UNKNOWN", nullable=False)
    provider_status: Mapped[str | None] = mapped_column(String(80))
    provider_role: Mapped[str | None] = mapped_column(String(32))
    provider_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    listing_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at_source: Mapped[str | None] = mapped_column(String(40))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=text("now()"), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_sync_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_logs.id", ondelete="SET NULL"))
    reconciliation_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at_provider: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    account: Mapped["EbayAccount"] = relationship(
        "EbayAccount",
        back_populates="offers"
    )

    conversation: Mapped["Conversation | None"] = relationship(
        "Conversation",
        back_populates="offers",
    )

    linked_message: Mapped["Message | None"] = relationship(
        "Message",
        back_populates="offers",
    )

    

    def __repr__(self) -> str:
        return f"<Offer {self.provider_offer_id} {self.status} {self.currency} {self.offer_amount}>"

    @property
    def buyer_message(self) -> str | None:
        payload = self.raw_payload if isinstance(self.raw_payload, dict) else {}
        message = payload.get("buyerMessage")

        if message:
            return str(message)

        if self.direction == OfferDirection.INCOMING and self.raw_text:
            return self.raw_text

        return None

    @property
    def seller_message(self) -> str | None:
        payload = self.raw_payload if isinstance(self.raw_payload, dict) else {}
        message = payload.get("sellerMessage")

        if message:
            return str(message)

        if self.direction == OfferDirection.OUTGOING and self.raw_text:
            return self.raw_text

        return None
