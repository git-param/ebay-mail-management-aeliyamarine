from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TaskCategoryPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    status: str = 'ACTIVE'
    quality_weight: float = Field(default=0, ge=0, le=100)
    display_order: int = 0


class SubtaskPayload(BaseModel):
    task_category_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    status: str = 'ACTIVE'
    display_order: int = 0
    source_type: str = 'MANUAL'
    source_reference_id: UUID | None = None
    source_configuration: dict | None = None
    count_method: str | None = None
    completion_rule: str | None = None
    supports_automatic_fetch: bool = False


class AssignmentPayload(BaseModel):
    user_id: UUID
    subtask_id: UUID
    quality_weight: float = Field(ge=0, le=100)
    effective_from: date
    effective_to: date | None = None
    auto_fetch_enabled: bool = True
    target_type: str = 'ANY_ACTIVITY'
    target_value: int | None = Field(default=None, ge=0)
    display_order: int = 0
    status: str = 'ACTIVE'


class CategoryAssignmentPayload(BaseModel):
    user_id: UUID
    task_category_id: UUID
    effective_from: date
    effective_to: date | None = None
    auto_fetch_enabled: bool = True
    target_type: str = 'ANY_ACTIVITY'
    target_value: int | None = Field(default=None, ge=0)
    display_order: int = 0
    status: str = 'ACTIVE'


class AssignmentResponse(AssignmentPayload):
    id: UUID
    subtask_name: str | None = None
    category_name: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubtaskResponse(SubtaskPayload):
    id: UUID
    assignment_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TaskCategoryResponse(TaskCategoryPayload):
    id: UUID
    subtasks: list[SubtaskResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserAssignmentSummary(BaseModel):
    user_id: UUID
    total_active_weight: float
    assignments: list[AssignmentResponse]
