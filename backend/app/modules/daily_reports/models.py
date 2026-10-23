import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class DailyWorkReport(Base):
    __tablename__ = 'daily_work_reports'
    __table_args__ = (
        UniqueConstraint('user_id', 'report_date', name='uq_daily_work_reports_user_date'),
        Index('ix_daily_work_reports_report_date', 'report_date'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    automatic_tasks: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    additional_tasks: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    report_text: Mapped[str] = mapped_column(Text, nullable=False)
    copied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    user = relationship('User')
