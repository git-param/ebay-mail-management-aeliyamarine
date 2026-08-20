import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class LeavePolicy(Base):
    __tablename__ = 'leave_policies'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paid_leave_per_month: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=1.5)
    instance_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    short_leave_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    instance_max_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    short_leave_max_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    office_start_time: Mapped[time] = mapped_column(Time, nullable=False, default=time(10, 0))
    office_end_time: Mapped[time] = mapped_column(Time, nullable=False, default=time(19, 0))
    attendance_deduction_per_excess: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=1)
    punctuality_deduction_per_extra_instance: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=1)
    short_leave_over_limit_action: Mapped[str] = mapped_column(String(20), nullable=False, default='BLOCK')
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, default=date(2026, 8, 1))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    updated_by = relationship('User', foreign_keys=[updated_by_user_id])


class LeaveRequest(Base):
    __tablename__ = 'leave_requests'
    __table_args__ = (
        Index('ix_leave_requests_user_month', 'user_id', 'start_date'),
        Index('ix_leave_requests_status', 'status'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    leave_type: Mapped[str] = mapped_column(String(30), nullable=False)
    day_part: Mapped[str | None] = mapped_column(String(20), nullable=True)
    instance_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    short_leave_pattern: Mapped[str | None] = mapped_column(String(30), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    duration_days: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='PENDING')
    paid_days: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    excess_days: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    pms_attendance_deduction: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    pms_punctuality_deduction: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    user = relationship('User', foreign_keys=[user_id])
    reviewed_by = relationship('User', foreign_keys=[reviewed_by_user_id])


class LeaveBalanceLedger(Base):
    __tablename__ = 'leave_balance_ledger'
    __table_args__ = (
        UniqueConstraint('source_request_id', 'entry_type', name='uq_leave_ledger_request_entry_type'),
        Index('ix_leave_ledger_user_month', 'user_id', 'year', 'month'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    source_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('leave_requests.id'), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    user = relationship('User', foreign_keys=[user_id])
    source_request = relationship('LeaveRequest')
    created_by = relationship('User', foreign_keys=[created_by_user_id])
