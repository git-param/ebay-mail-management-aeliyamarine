from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


def clean_keywords(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    cleaned = [' '.join(value.strip().split()) for value in values if value and value.strip()]
    if any(len(value) > 120 for value in cleaned):
        raise ValueError('Message type keywords cannot exceed 120 characters')
    return cleaned


class MessageTypeCreate(BaseModel):
    """Validate user-managed fields for an automatically ordered message type."""
    name: str = Field(min_length=1, max_length=160)
    parent_id: UUID | None = None
    description: str | None = None
    is_active: bool = True
    keywords: list[str] = Field(default_factory=list)

    @field_validator('keywords')
    @classmethod
    def validate_keywords(cls, values):
        return clean_keywords(values)


class MessageTypeUpdate(BaseModel):
    """Validate editable message-type fields while preserving system ordering."""
    name: str | None = Field(default=None, min_length=1, max_length=160)
    parent_id: UUID | None = None
    description: str | None = None
    keywords: list[str] | None = None

    @field_validator('keywords')
    @classmethod
    def validate_keywords(cls, values):
        return clean_keywords(values)


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
    keywords: list[str] = Field(default_factory=list)
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
