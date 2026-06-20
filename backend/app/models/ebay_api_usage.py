import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class EbayApiUsage(Base):
    __tablename__ = 'ebay_api_usage'
    __table_args__ = (UniqueConstraint('usage_date', name='uq_ebay_api_usage_date'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
