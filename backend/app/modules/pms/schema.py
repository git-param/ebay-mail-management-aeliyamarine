from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ----------------------------------------------------------------------
# PMS Configuration
# ----------------------------------------------------------------------

class PmsMetricConfigBase(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    weight: float = Field(ge=0)
    source: str = 'MANUAL'
    is_auto_calculated: bool = False
    is_manually_editable: bool = True
    is_active: bool = True
    display_order: int = 0
    description: str | None = None


class PmsMetricConfigCreate(PmsMetricConfigBase):
    pass


class PmsMetricConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    weight: float | None = Field(default=None, ge=0)
    is_manually_editable: bool | None = None
    is_active: bool | None = None
    display_order: int | None = None
    description: str | None = None


class PmsMetricConfigResponse(PmsMetricConfigBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class PmsMetricConfigListResponse(BaseModel):
    items: list[PmsMetricConfigResponse]
    total_active_weight: float


# ----------------------------------------------------------------------
# Monthly PMS
# ----------------------------------------------------------------------

class PmsMonthlyMetricSchema(BaseModel):
    metric_key: str
    metric_name_snapshot: str
    weight_snapshot: float
    source_snapshot: str
    is_auto_calculated_snapshot: bool
    auto_value: float | None = None
    final_value: float = 0
    was_overridden: bool = False
    calc_meta: dict | None = None


class PmsMonthlyRecordResponse(BaseModel):
    id: UUID | None = None
    user_id: UUID
    user_name: str
    user_email: str | None = None
    year: int
    month: int
    status: str = 'DRAFT'
    final_score: float = 0
    maximum_score: float = 0
    remarks: str | None = None
    metrics: list[PmsMonthlyMetricSchema] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    updated_by_name: str | None = None


class PmsMonthlyTableRow(BaseModel):
    user_id: UUID
    user_name: str
    user_email: str | None = None
    record_id: UUID | None = None
    status: str | None = None
    final_score: float | None = None
    maximum_score: float | None = None
    metrics: list[PmsMonthlyMetricSchema] = Field(default_factory=list)


class PmsMonthlyTableResponse(BaseModel):
    year: int
    month: int
    total_active_weight: float
    items: list[PmsMonthlyTableRow]
    completed_count: int
    pending_count: int
    average_score: float | None = None
    top_performer_name: str | None = None
    top_performer_score: float | None = None


class PmsMonthlyMetricInput(BaseModel):
    metric_key: str
    final_value: float = Field(ge=0)
    target_percent: float | None = Field(default=None, ge=0, le=100)


class PmsMonthlySaveRequest(BaseModel):
    user_id: UUID
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    remarks: str | None = None
    status: str = 'COMPLETED'
    metrics: list[PmsMonthlyMetricInput]

    @field_validator('status')
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in {'DRAFT', 'COMPLETED'}:
            raise ValueError('status must be DRAFT or COMPLETED')
        return value


class PmsMonthlyRefreshRequest(BaseModel):
    user_id: UUID
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


# ----------------------------------------------------------------------
# History
# ----------------------------------------------------------------------

class PmsHistoryItem(BaseModel):
    record_id: UUID
    user_id: UUID
    user_name: str
    year: int
    month: int
    status: str
    final_score: float
    maximum_score: float
    percentage: float
    updated_at: datetime


class PmsHistoryResponse(BaseModel):
    items: list[PmsHistoryItem]
    total: int


# ----------------------------------------------------------------------
# Employee of the Month
# ----------------------------------------------------------------------

class PmsEmployeeOfMonthCandidate(BaseModel):
    user_id: UUID
    user_name: str
    final_score: float


class PmsEmployeeOfMonthResponse(BaseModel):
    year: int
    month: int
    is_tie: bool = False
    candidates: list[PmsEmployeeOfMonthCandidate] = Field(default_factory=list)
    winner: PmsMonthlyRecordResponse | None = None


class PmsEmployeeOfMonthResolveRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    selected_user_id: UUID
    reason: str | None = None


class PmsEmployeeOfMonthWin(BaseModel):
    year: int
    month: int
    final_score: float


class PmsEmployeeOfMonthStatsItem(BaseModel):
    user_id: UUID
    user_name: str
    user_email: str | None = None
    win_count: int
    wins: list[PmsEmployeeOfMonthWin] = Field(default_factory=list)


class PmsEmployeeOfMonthStatsResponse(BaseModel):
    items: list[PmsEmployeeOfMonthStatsItem]
