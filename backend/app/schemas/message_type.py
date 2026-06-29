from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class MessageTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    parent_id: UUID | None = None
    description: str | None = None
    display_order: int = Field(default=0, ge=0)
    is_active: bool = True


class MessageTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    parent_id: UUID | None = None
    description: str | None = None
    display_order: int | None = Field(default=None, ge=0)


class MessageTypeStatus(BaseModel):
    is_active: bool | None = None
    restore: bool = False


class MessageTypeResponse(BaseModel):
    id: UUID
    name: str
    parent_id: UUID | None
    description: str | None
    display_order: int
    is_active: bool
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    children: list['MessageTypeResponse'] = Field(default_factory=list)


class ClassificationReportRow(BaseModel):
    id: UUID
    created_at: datetime
    conversation_id: UUID
    conversation_message_id: UUID
    provider_conversation_id: str
    buyer: str | None
    seller: str | None
    seller_account_id: UUID | None
    user_id: UUID
    agent: str
    category: str
    category_id: UUID
    subcategory: str | None
    subcategory_id: UUID | None
    message_preview: str


class ClassificationReport(BaseModel):
    items: list[ClassificationReportRow]
    total: int
    limit: int
    offset: int
    summary: list[dict]
    messages_per_day: list[dict]
    messages_by_employee: list[dict]
    messages_by_category: list[dict]
    messages_by_seller_account: list[dict]
