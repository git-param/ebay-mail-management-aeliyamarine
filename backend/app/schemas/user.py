from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.constants.auth_constants import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH


class UserCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    role: str
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    role: str
    is_active: bool


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login: datetime | None = None
