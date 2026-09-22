from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DailyEntryTaskLimits(BaseModel):
    sla_max: int = 20


class DailyEntryScoreBreakdownItem(BaseModel):
    label: str
    count: int = 0
    # Present for breakdown rows sourced from individual conversations (currently
    # Message Type activity) so the tooltip can link straight to each one, even
    # when no SLA cycle was ever opened for that reply.
    conversation_ids: list[UUID] | None = None


class DailyEntryScoreItem(BaseModel):
    key: str
    label: str
    value: float = Field(default=0, ge=0)
    max_score: float = Field(default=10, gt=0)
    status: str = 'NOT_ENTERED'
    source: str = 'MANUAL'
    activity_count: int | None = None
    message_type_id: UUID | None = None
    subtask_id: UUID | None = None
    sub_subtask_id: UUID | None = None
    # Per-source fetched breakdown for catch-all items (currently Other General
    # Work). Preserved even after the Admin manually edits `value`.
    breakdown: list[DailyEntryScoreBreakdownItem] | None = None


class DailyEntryBase(BaseModel):
    entry_date: date
    day_type: str = 'WORKING_DAY'
    final_score_percent: int = Field(default=0, ge=0)
    sla_score: int = Field(default=0, ge=0, le=20)
    sla_met_count: int | None = None
    sla_total_count: int | None = None
    sla_auto_fetched: bool = False
    score_items: list[DailyEntryScoreItem] = Field(default_factory=list)
    error_level: str = 'NO_ERROR'
    error_remark: str | None = None
    remarks: str | None = None
    particulars_error_note: str | None = None
    sla_remarks: str | None = None


class DailyEntryCreate(DailyEntryBase):
    user_id: UUID


class DailyEntryResponse(DailyEntryBase):
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


class DailyEntryDraftResponse(BaseModel):
    entry: DailyEntryBase
    limits: DailyEntryTaskLimits
    existing_entry_id: UUID | None = None


class DailyEntryListResponse(BaseModel):
    items: list[DailyEntryResponse]
    total: int
    limits: DailyEntryTaskLimits


class DailyEntryLoadRequestUser(BaseModel):
    id: UUID
    full_name: str | None = None
    email: str | None = None


class DailyEntryLoadResponseItem(BaseModel):
    user: DailyEntryLoadRequestUser
    entry: DailyEntryBase
    existing_entry_id: UUID | None = None


class DailyEntryLoadResponse(BaseModel):
    entry_date: date
    limits: DailyEntryTaskLimits
    items: list[DailyEntryLoadResponseItem]


class DailyEntryUploadEntry(DailyEntryCreate):
    pass


class DailyEntryUploadRequest(BaseModel):
    entries: list[DailyEntryUploadEntry] = Field(min_length=1)


class DailyEntryUploadResultItem(BaseModel):
    user_id: UUID
    success: bool
    entry_id: UUID | None = None
    error: str | None = None


class DailyEntryUploadResponse(BaseModel):
    results: list[DailyEntryUploadResultItem]


class DailyEntryBulkDeleteRequest(BaseModel):
    date_from: date
    date_to: date
    user_id: UUID | None = None


class DailyEntryBulkDeleteResponse(BaseModel):
    deleted_count: int
    date_from: date
    date_to: date
    user_id: UUID | None = None


class DailyEntrySLAReviewItem(BaseModel):
    id: UUID
    conversation_id: UUID
    cycle_number: int
    buyer: str | None = None
    provider_conversation_id: str | None = None
    seller: str | None = None
    buyer_message_time: datetime
    replied_time: datetime | None = None
    response_duration_seconds: int | None = None
    sla_met: bool | None = None


class DailyEntrySLAReviewResponse(BaseModel):
    user_id: UUID
    entry_date: date
    met_count: int
    total_count: int
    items: list[DailyEntrySLAReviewItem]
