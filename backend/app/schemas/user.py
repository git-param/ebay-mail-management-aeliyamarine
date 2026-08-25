from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.constants.auth_constants import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH


class UserCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    role: str
    is_active: bool = True
    employee_id: str = Field(min_length=1, max_length=60)
    department: str = Field(min_length=1, max_length=120)
    designation: str = Field(min_length=1, max_length=120)
    date_of_joining: date


class UserUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    role: str
    is_active: bool
    employee_id: str = Field(min_length=1, max_length=60)
    department: str = Field(min_length=1, max_length=120)
    designation: str = Field(min_length=1, max_length=120)
    date_of_joining: date


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    role: str
    is_active: bool
    employee_id: str | None = None
    department: str | None = None
    designation: str | None = None
    date_of_joining: date | None = None
    created_at: datetime
    updated_at: datetime
    last_login: datetime | None = None
    assigned_categories: list[str] = Field(default_factory=list)
    assigned_category_ids: list[UUID] = Field(default_factory=list)
