from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ReportTask(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: int = Field(ge=1, le=100000)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = ' '.join(value.split())
        if not value:
            raise ValueError('Task name is required')
        return value


class ReportTasksUpdate(BaseModel):
    report_date: date
    tasks: list[ReportTask] = Field(max_length=30)

    @field_validator('tasks')
    @classmethod
    def unique_names(cls, tasks: list[ReportTask]) -> list[ReportTask]:
        names = [task.name.casefold() for task in tasks]
        if len(names) != len(set(names)):
            raise ValueError('Each task name must be unique for the day')
        return tasks


class ReportCopyRequest(BaseModel):
    report_date: date


class DailyReportResponse(BaseModel):
    id: UUID | None = None
    user_id: UUID
    user_name: str
    report_date: date
    automatic_tasks: list[ReportTask]
    additional_tasks: list[ReportTask]
    report_text: str
    copied_at: datetime | None = None
    editable: bool


class DailyReportListResponse(BaseModel):
    items: list[DailyReportResponse]
    total: int


class DailyReportUser(BaseModel):
    id: UUID
    full_name: str
