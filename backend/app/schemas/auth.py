from pydantic import BaseModel, EmailStr, Field

from app.constants.auth_constants import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class UserSession(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    must_reset_password: bool


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'
    expires_in: int
    user: UserSession


class MessageResponse(BaseModel):
    message: str
