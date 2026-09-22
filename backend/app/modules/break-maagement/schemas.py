from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BreakStartRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=120)


class BreakSessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    user_name: str
    user_role: str
    reason: str
    start_time: datetime
    end_time: datetime | None = None
    duration_minutes: int | None = None

    class Config:
        from_attributes = True


class BreakStatusResponse(BaseModel):
    is_on_break: bool
    active_break: BreakSessionResponse | None = None


class BreakHistoryResponse(BaseModel):
    items: list[BreakSessionResponse]
    total: int


class BreakOverviewUser(BaseModel):
    user_id: UUID
    user_name: str
    user_role: str
    is_on_break: bool
    active_reason: str | None = None
    active_start_time: datetime | None = None
    total_break_minutes_today: int
    today_breaks: list[BreakSessionResponse]


class BreakOverviewSection(BaseModel):
    role_key: str
    title: str
    users: list[BreakOverviewUser]


class BreakOverviewResponse(BaseModel):
    date: date
    sections: list[BreakOverviewSection]
