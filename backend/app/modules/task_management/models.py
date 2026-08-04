import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class TaskStatus(str, enum.Enum):
    ACTIVE = 'ACTIVE'
    INACTIVE = 'INACTIVE'
    ARCHIVED = 'ARCHIVED'


class SubtaskSourceType(str, enum.Enum):
    MESSAGE_TYPE = 'MESSAGE_TYPE'
    SOLD_POSTING = 'SOLD_POSTING'
    OFFER_MANAGEMENT = 'OFFER_MANAGEMENT'
    OTHER_GENERAL_WORK = 'OTHER_GENERAL_WORK'
    MANUAL = 'MANUAL'


class AssignmentTargetType(str, enum.Enum):
    ANY_ACTIVITY = 'ANY_ACTIVITY'
    FIXED_COUNT = 'FIXED_COUNT'
    COMPLETION_PERCENTAGE = 'COMPLETION_PERCENTAGE'
    MANUAL = 'MANUAL'


class TaskCategory(Base):
    __tablename__ = 'task_categories'
    __table_args__ = (Index('ix_task_categories_status_order', 'status', 'display_order'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus, name='task_status'), nullable=False, default=TaskStatus.ACTIVE)
    quality_weight: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    subtasks = relationship('Subtask', back_populates='category', cascade='all, delete-orphan', order_by='Subtask.display_order')
    created_by = relationship('User', foreign_keys=[created_by_user_id])
    updated_by = relationship('User', foreign_keys=[updated_by_user_id])


class Subtask(Base):
    __tablename__ = 'subtasks'
    __table_args__ = (
        Index('ix_subtasks_category_order', 'task_category_id', 'display_order'),
        Index('ix_subtasks_source_type', 'source_type'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('task_categories.id'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus, name='task_status'), nullable=False, default=TaskStatus.ACTIVE)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_type: Mapped[SubtaskSourceType] = mapped_column(Enum(SubtaskSourceType, name='subtask_source_type'), nullable=False, default=SubtaskSourceType.MANUAL)
    source_reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_configuration: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    count_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    completion_rule: Mapped[str | None] = mapped_column(String(80), nullable=True)
    supports_automatic_fetch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    category = relationship('TaskCategory', back_populates='subtasks')
    assignments = relationship('UserSubtaskAssignment', back_populates='subtask', cascade='all, delete-orphan')
    created_by = relationship('User', foreign_keys=[created_by_user_id])
    updated_by = relationship('User', foreign_keys=[updated_by_user_id])


class UserSubtaskAssignment(Base):
    __tablename__ = 'user_subtask_assignments'
    __table_args__ = (
        UniqueConstraint('user_id', 'subtask_id', 'effective_from', name='uq_user_subtask_assignment_effective_from'),
        Index('ix_user_subtask_assignments_user_dates', 'user_id', 'effective_from', 'effective_to'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    subtask_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('subtasks.id'), nullable=False, index=True)
    quality_weight: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    auto_fetch_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    target_type: Mapped[AssignmentTargetType] = mapped_column(Enum(AssignmentTargetType, name='assignment_target_type'), nullable=False, default=AssignmentTargetType.ANY_ACTIVITY)
    target_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus, name='task_status'), nullable=False, default=TaskStatus.ACTIVE)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    user = relationship('User', foreign_keys=[user_id])
    subtask = relationship('Subtask', back_populates='assignments')
    created_by = relationship('User', foreign_keys=[created_by_user_id])
    updated_by = relationship('User', foreign_keys=[updated_by_user_id])