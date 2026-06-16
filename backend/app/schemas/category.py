from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CategoryKeywordResponse(BaseModel):
    id: UUID
    category_id: UUID
    keyword: str
    created_at: datetime


class CategoryBaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    color: str = Field(min_length=1, max_length=20)
    sla_hours: int = Field(ge=1)
    keywords: list[str] = Field(default_factory=list)

    @field_validator('name', 'color')
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator('description')
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator('keywords')
    @classmethod
    def strip_keywords(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]


class CategoryCreateRequest(CategoryBaseRequest):
    pass


class CategoryUpdateRequest(CategoryBaseRequest):
    is_active: bool | None = None


class CategoryKeywordCreateRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=120)

    @field_validator('keyword')
    @classmethod
    def strip_keyword(cls, value: str) -> str:
        return value.strip()


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    color: str
    sla_hours: int
    is_active: bool
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    keywords: list[CategoryKeywordResponse]
    keywords_count: int
