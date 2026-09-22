from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ReplyTemplateCreateRequest(BaseModel):
    """Payload for creating a reusable reply template."""

    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=5000)
    category_id: UUID | None = None
    is_active: bool = True


class ReplyTemplateUpdateRequest(BaseModel):
    """Payload for updating a reusable reply template."""

    title: str | None = Field(default=None, min_length=1, max_length=160)
    body: str | None = Field(default=None, min_length=1, max_length=5000)
    category_id: UUID | None = None
    is_active: bool | None = None


class ReplyTemplateCategoryCreateRequest(BaseModel):
    """Payload for creating a reply template category."""

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class ReplyTemplateCategoryUpdateRequest(BaseModel):
    """Payload for updating a reply template category."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class ReplyTemplateCategorySummary(BaseModel):
    """Compact category representation embedded in a template response."""

    id: UUID
    name: str
    is_active: bool


class ReplyTemplateCategoryResponse(BaseModel):
    """API representation of a reply template category."""

    id: UUID
    name: str
    description: str | None = None
    is_active: bool
    created_by: UUID | None = None
    updated_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ReplyTemplateResponse(BaseModel):
    """API representation of a reply template."""

    id: UUID
    title: str
    body: str
    category_id: UUID | None = None
    category: ReplyTemplateCategorySummary | None = None
    is_active: bool
    created_by: UUID | None = None
    updated_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class PermissionResponse(BaseModel):
    """API representation of a role permission grant."""

    code: str
    description: str | None = None


class RolePermissionUpdateRequest(BaseModel):
    """Payload for replacing a role's permission set."""

    permission_codes: list[str] = Field(default_factory=list, max_length=100)
