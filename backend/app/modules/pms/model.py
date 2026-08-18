import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class PmsMetricSource(str, enum.Enum):
    """
    Where a metric's value originates from.
    MANUAL             -> Admin types the score directly (Target, Attendance, Punctuality, Competency).
    PRODUCTIVITY_AUTO   -> derived from Daily Task Entry score_items (task completion).
    QUALITY_AUTO        -> derived from Daily Task Entry sla_score / error_level.
    CUSTOM              -> reserved for future auto sources without a schema change.
    """

    MANUAL = 'MANUAL'
    PRODUCTIVITY_AUTO = 'PRODUCTIVITY_AUTO'
    QUALITY_AUTO = 'QUALITY_AUTO'
    CUSTOM = 'CUSTOM'


class PmsMonthlyStatus(str, enum.Enum):
    # DRAFT: Admin has loaded/started the month but not finalized it.
    # COMPLETED: authoritative for Employee of the Month + history reporting.
    DRAFT = 'DRAFT'
    COMPLETED = 'COMPLETED'


class PmsMetricConfig(Base):
    """
    Admin-configurable metric definitions (weights, source, active flag).
    Deactivate instead of deleting when historical PmsMonthlyMetric rows
    reference a metric_key — deleting would not remove history (metrics are
    snapshotted per month) but would remove the ability to reconfigure it.
    """

    __tablename__ = 'pms_metric_configs'
    __table_args__ = (
        UniqueConstraint('key', name='uq_pms_metric_configs_key'),
        Index('ix_pms_metric_configs_display_order', 'display_order'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    source: Mapped[PmsMetricSource] = mapped_column(Enum(PmsMetricSource, name='pms_metric_source'), nullable=False, default=PmsMetricSource.MANUAL)
    is_auto_calculated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_manually_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    created_by = relationship('User', foreign_keys=[created_by_user_id])
    updated_by = relationship('User', foreign_keys=[updated_by_user_id])


class PmsMonthlyRecord(Base):
    """
    One row per employee per month. The authoritative final_score/maximum_score
    live here; the per-metric breakdown lives in PmsMonthlyMetric so historical
    configuration is preserved even if PmsMetricConfig changes later.
    """

    __tablename__ = 'pms_monthly_records'
    __table_args__ = (
        UniqueConstraint('user_id', 'year', 'month', name='uq_pms_monthly_records_user_year_month'),
        Index('ix_pms_monthly_records_year_month', 'year', 'month'),
        Index('ix_pms_monthly_records_user_id', 'user_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PmsMonthlyStatus] = mapped_column(Enum(PmsMonthlyStatus, name='pms_monthly_status'), nullable=False, default=PmsMonthlyStatus.DRAFT)
    final_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    maximum_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    user = relationship('User', foreign_keys=[user_id])
    created_by = relationship('User', foreign_keys=[created_by_user_id])
    updated_by = relationship('User', foreign_keys=[updated_by_user_id])
    metrics = relationship(
        'PmsMonthlyMetric',
        back_populates='record',
        cascade='all, delete-orphan',
        order_by='PmsMonthlyMetric.created_at',
    )


class PmsMonthlyMetric(Base):
    """
    Per-metric snapshot for a PmsMonthlyRecord. Every field here is frozen at
    save time so a later PmsMetricConfig change (weight, name, source) never
    alters an already-saved month.
    """

    __tablename__ = 'pms_monthly_metrics'
    __table_args__ = (Index('ix_pms_monthly_metrics_record_id', 'pms_monthly_record_id'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pms_monthly_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('pms_monthly_records.id', ondelete='CASCADE'), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(60), nullable=False)
    metric_name_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    weight_snapshot: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    source_snapshot: Mapped[str] = mapped_column(String(30), nullable=False)
    is_auto_calculated_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Original system-computed value before any Admin edit. Null for pure-manual metrics.
    auto_value: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    # Value actually used in final_score (== auto_value unless overridden, or the
    # Admin-typed value for manual metrics).
    final_value: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    was_overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Free-form calculation context surfaced in the UI tooltip, e.g. working days
    # counted, SLA average %, minor/major error day counts. Never used in scoring
    # math itself, purely explanatory.
    calc_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    record = relationship('PmsMonthlyRecord', back_populates='metrics')


class PmsEmployeeOfMonthSelection(Base):
    """
    Tracks Employee of the Month resolution per (year, month). Auto-populated
    with the unique top scorer when there's no tie; left for Admin resolution
    (selected_user_id null, is_tie true) when multiple employees share the
    top COMPLETED score, so a winner is never picked at random.
    """

    __tablename__ = 'pms_employee_of_month_selections'
    __table_args__ = (UniqueConstraint('year', 'month', name='uq_pms_eom_year_month'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    is_tie: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tied_user_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    selected_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    selected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    selected_user = relationship('User', foreign_keys=[selected_user_id])
    selected_by = relationship('User', foreign_keys=[selected_by_user_id])