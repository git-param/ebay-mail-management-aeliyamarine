from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


LEAVE_TYPES = {'PAID', 'INSTANCE', 'SHORT'}
STATUSES = {'PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'}
DAY_PARTS = {'FULL', 'HALF'}
INSTANCE_KINDS = {'LATE_ARRIVAL', 'EARLY_DEPARTURE'}
SHORT_PATTERNS = {'LATE_LOGIN', 'MID_DAY_LEAVE', 'EARLY_EXIT', 'EARLY_EXIT_WITH_BREAK'}


class LeavePolicyResponse(BaseModel):
    id: UUID
    paid_leave_per_month: float
    instance_limit: int
    short_leave_limit: int
    instance_max_minutes: int
    short_leave_max_minutes: int
    office_start_time: time
    office_end_time: time
    attendance_deduction_per_excess: float
    punctuality_deduction_per_extra_instance: float
    short_leave_over_limit_action: str
    effective_from: date
    updated_at: datetime


class LeavePolicyUpdate(BaseModel):
    paid_leave_per_month: float | None = Field(default=None, ge=0)
    instance_limit: int | None = Field(default=None, ge=0)
    short_leave_limit: int | None = Field(default=None, ge=0)
    instance_max_minutes: int | None = Field(default=None, ge=1)
    short_leave_max_minutes: int | None = Field(default=None, ge=1)
    office_start_time: time | None = None
    office_end_time: time | None = None
    attendance_deduction_per_excess: float | None = Field(default=None, ge=0)
    punctuality_deduction_per_extra_instance: float | None = Field(default=None, ge=0)
    short_leave_over_limit_action: str | None = None


class LeaveRequestCreate(BaseModel):
    leave_type: str
    start_date: date
    end_date: date | None = None
    day_part: str | None = None
    instance_kind: str | None = None
    short_leave_pattern: str | None = None
    start_time: time | None = None
    end_time: time | None = None
    reason: str = Field(min_length=2, max_length=2000)

    @field_validator('leave_type')
    @classmethod
    def validate_leave_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in LEAVE_TYPES:
            raise ValueError('leave_type must be PAID, INSTANCE, or SHORT')
        return normalized


class LeaveReviewRequest(BaseModel):
    status: str
    review_note: str | None = Field(default=None, max_length=2000)

    @field_validator('status')
    @classmethod
    def validate_status(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {'APPROVED', 'REJECTED'}:
            raise ValueError('status must be APPROVED or REJECTED')
        return normalized


class LeaveRequestResponse(BaseModel):
    id: UUID
    user_id: UUID
    user_name: str | None = None
    user_email: str | None = None
    leave_type: str
    day_part: str | None = None
    instance_kind: str | None = None
    short_leave_pattern: str | None = None
    start_date: date
    end_date: date
    start_time: time | None = None
    end_time: time | None = None
    duration_days: float
    duration_minutes: int
    reason: str
    status: str
    paid_days: float
    excess_days: float
    pms_attendance_deduction: float
    pms_punctuality_deduction: float
    reviewed_by_user_id: UUID | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime
    updated_at: datetime


class LeaveRequestListResponse(BaseModel):
    items: list[LeaveRequestResponse]
    total: int


class LeaveBalanceResponse(BaseModel):
    user_id: UUID
    user_name: str | None = None
    user_email: str | None = None
    year: int
    month: int
    paid_accrued: float
    paid_used: float
    paid_available: float
    excess_paid_occurrences: int
    instance_used: int
    instance_remaining: int
    short_used: int
    short_remaining: int
    pms_attendance_deduction: float
    pms_punctuality_deduction: float


class LeaveImpactResponse(BaseModel):
    user_id: UUID
    year: int
    month: int
    attendance_deduction: float
    punctuality_deduction: float
    excess_paid_occurrences: int
    approved_instances: int
    extra_instances: int


class LeaveAdminSummaryRow(BaseModel):
    user_id: UUID
    employee: str
    year: int
    month: int
    paid_leaves: float
    unpaid_leaves: float
    adh: int
    is_overridden: bool = False


class LeaveAdminSummaryUpdateItem(BaseModel):
    user_id: UUID
    paid_leaves: float = Field(ge=0)
    unpaid_leaves: float = Field(ge=0)
    adh: int = Field(ge=0)


class LeaveAdminSummaryUpdate(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    items: list[LeaveAdminSummaryUpdateItem]
