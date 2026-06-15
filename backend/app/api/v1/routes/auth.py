from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.constants.auth_constants import AuthMessages
from app.db.session import get_db
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.services.auth_service import AuthService


router = APIRouter()


@router.post('/login', response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    return AuthService(db).login(
        email=payload.email,
        password=payload.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
    )


@router.post('/refresh', response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return AuthService(db).refresh(refresh_token=payload.refresh_token)


@router.post('/logout', response_model=MessageResponse)
def logout(
    payload: LogoutRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> MessageResponse:
    AuthService(db).logout(refresh_token=payload.refresh_token, user_id=current_user.id)
    return MessageResponse(message=AuthMessages.LOGOUT_SUCCESS)


@router.post('/forgot-password', response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    AuthService(db).request_password_reset(email=payload.email)
    return MessageResponse(message=AuthMessages.PASSWORD_RESET_SENT)


@router.post('/reset-password', response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    AuthService(db).reset_password(token=payload.token, new_password=payload.new_password)
    return MessageResponse(message=AuthMessages.PASSWORD_RESET_SUCCESS)
