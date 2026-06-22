from pydantic import BaseModel, EmailStr, Field

from app.constants.auth_constants import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class RefreshRequest(BaseModel):
    """Optional refresh token payload for legacy non-cookie clients."""

    refresh_token: str | None = None


class LogoutRequest(BaseModel):
    """Optional logout payload for legacy non-cookie clients."""

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
    """Authentication response with tokens delivered through HttpOnly cookies."""

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = 'bearer'
    expires_in: int
    user: UserSession


class MessageResponse(BaseModel):
    message: str
