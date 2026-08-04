from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PMSTaskLimits(BaseModel):
    sla_max: int = 20


class PMSScoreItem(BaseModel):
    key: str
    label: str
    value: int = Field(default=0, ge=0)
    max_score: int = Field(default=10, ge=1)
    status: str = 'NOT_ENTERED'
    source: str = 'MANUAL'
    activity_count: int | None = None
    message_type_id: UUID | None = None
    subtask_id: UUID | None = None


class PMSDailyEntryBase(BaseModel):
    entry_date: date
    day_type: str = 'WORKING_DAY'
    final_score_percent: int = Field(default=0, ge=0)
    sla_score: int = Field(default=0, ge=0, le=20)
    score_items: list[PMSScoreItem] = Field(default_factory=list)
    error_level: str = 'NO_ERROR'
    error_remark: str | None = None
    remarks: str | None = None
    feedback_status: str = 'GIVEN'
    particulars_error_note: str | None = None
    sla_remarks: str | None = None


class PMSDailyEntryCreate(PMSDailyEntryBase):
    user_id: UUID


class PMSDailyEntryResponse(PMSDailyEntryBase):
    id: UUID
    user_id: UUID
    user_name: str
    user_email: str | None = None
    created_by_user_id: UUID | None = None
    updated_by_user_id: UUID | None = None
    created_by_name: str | None = None
    updated_by_name: str | None = None
    created_at: datetime
    updated_at: datetime


class PMSDraftResponse(BaseModel):
    entry: PMSDailyEntryBase
    limits: PMSTaskLimits
    existing_entry_id: UUID | None = None


class PMSListResponse(BaseModel):
    items: list[PMSDailyEntryResponse]
    total: int
    limits: PMSTaskLimits


class PMSLoadRequestUser(BaseModel):
    id: UUID
    full_name: str | None = None
    email: str | None = None


class PMSLoadResponseItem(BaseModel):
    user: PMSLoadRequestUser
    entry: PMSDailyEntryBase
    existing_entry_id: UUID | None = None


class PMSLoadResponse(BaseModel):
    entry_date: date
    limits: PMSTaskLimits
    items: list[PMSLoadResponseItem]


class PMSUploadEntry(PMSDailyEntryCreate):
    pass


class PMSUploadRequest(BaseModel):
    entries: list[PMSUploadEntry] = Field(min_length=1)


class PMSUploadResultItem(BaseModel):
    user_id: UUID
    success: bool
    entry_id: UUID | None = None
    error: str | None = None


class PMSUploadResponse(BaseModel):
    results: list[PMSUploadResultItem]