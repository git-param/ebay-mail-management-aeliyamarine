import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
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


class PMSErrorLevel(str, enum.Enum):
    NO_ERROR = 'NO_ERROR'
    MINOR = 'MINOR'
    MAJOR = 'MAJOR'


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
    # Legacy fixed-column scores. No longer populated by the service (score_items is the
    # source of truth) but retained on the model/table for backward compatibility with any
    # other consumers that may still read these columns directly.
    sold_posting_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    m2m_vip_followups_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tracking_sheet_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purchase_sheet_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    booking_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    other_general_work_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_score_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sla_score: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    score_items: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    error_level: Mapped[PMSErrorLevel] = mapped_column(Enum(PMSErrorLevel, name='pms_error_level'), nullable=False, default=PMSErrorLevel.NO_ERROR)
    error_remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_status: Mapped[PMSFeedbackStatus] = mapped_column(Enum(PMSFeedbackStatus, name='pms_feedback_status'), nullable=False, default=PMSFeedbackStatus.GIVEN)
    particulars_error_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sla_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    user = relationship('User', foreign_keys=[user_id])
    created_by = relationship('User', foreign_keys=[created_by_user_id])
    updated_by = relationship('User', foreign_keys=[updated_by_user_id])


class PMSDailyTaskEntryHistory(Base):
    __tablename__ = 'pms_daily_task_entry_history'
    __table_args__ = (Index('ix_pms_daily_task_entry_history_entry_id', 'entry_id'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('pms_daily_task_entries.id', ondelete='CASCADE'), nullable=False)
    changed_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    entry = relationship('PMSDailyTaskEntry')
    changed_by = relationship('User')