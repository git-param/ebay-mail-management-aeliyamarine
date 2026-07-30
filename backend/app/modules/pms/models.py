import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class PMSDayType(str, enum.Enum):
    WORKING_DAY = 'WORKING_DAY'
    HOLIDAY = 'HOLIDAY'
    SUNDAY = 'SUNDAY'
    LEAVE = 'LEAVE'


class PMSFeedbackStatus(str, enum.Enum):
    GIVEN = 'GIVEN'
    PENDING = 'PENDING'


class PMSDailyTaskEntry(Base):
    __tablename__ = 'pms_daily_task_entries'
    __table_args__ = (
        UniqueConstraint('user_id', 'entry_date', name='uq_pms_daily_task_entries_user_date'),
        Index('ix_pms_daily_task_entries_user_id', 'user_id'),
        Index('ix_pms_daily_task_entries_entry_date', 'entry_date'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    day_type: Mapped[PMSDayType] = mapped_column(Enum(PMSDayType, name='pms_day_type'), nullable=False, default=PMSDayType.WORKING_DAY)
    sold_posting_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    m2m_vip_followups_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tracking_sheet_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purchase_sheet_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    booking_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    other_general_work_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_score_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sla_score: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    feedback_status: Mapped[PMSFeedbackStatus] = mapped_column(Enum(PMSFeedbackStatus, name='pms_feedback_status'), nullable=False, default=PMSFeedbackStatus.GIVEN)
    particulars_error_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sla_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    user = relationship('User')
