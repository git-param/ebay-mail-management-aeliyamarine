"""Durable intent/result ledger; never duplicate provider offer storage."""
import uuid
from datetime import UTC, datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Index, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base


class EbayBestOfferAction(Base):
    __tablename__ = 'ebay_best_offer_actions'
    __table_args__ = (
        Index('uq_best_offer_unresolved_action', 'offer_id', unique=True,
              postgresql_where=text("state IN ('PREPARED','DISPATCHING','RECONCILIATION_REQUIRED')")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    offer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('offers.id'), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('ebay_accounts.id'))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    expected_version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16))
    parameters: Mapped[dict] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(40), default='PREPARED', index=True)
    provider_result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
