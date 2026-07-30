from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PMSTaskLimits(BaseModel):
    sold_posting: int = 20
    m2m_vip_followups: int = 25
    tracking_sheet: int = 25
    purchase_sheet: int = 10
    booking: int = 10
    other_general_work: int = 10


class PMSDailyEntryBase(BaseModel):
    entry_date: date
    day_type: str = 'WORKING_DAY'
    sold_posting_score: int = Field(default=0, ge=0)
    m2m_vip_followups_score: int = Field(default=0, ge=0)
    tracking_sheet_score: int = Field(default=0, ge=0)
    purchase_sheet_score: int = Field(default=0, ge=0)
    booking_score: int = Field(default=0, ge=0)
    other_general_work_score: int = Field(default=0, ge=0)
    final_score_percent: int = Field(default=0, ge=0)
    sla_score: int = Field(default=20, ge=0, le=20)
    feedback_status: str = 'GIVEN'
    particulars_error_note: str | None = None
    sla_remarks: str | None = None


class PMSDailyEntryCreate(PMSDailyEntryBase):
    user_id: UUID | None = None


class PMSDailyEntryResponse(PMSDailyEntryBase):
    id: UUID
    user_id: UUID
    user_name: str
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
