from fastapi import APIRouter, Body, Cookie, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.constants.auth_constants import AuthMessages
from app.core.config import get_settings
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
ACCESS_COOKIE_NAME = 'access_token'
REFRESH_COOKIE_NAME = 'refresh_token'


def set_auth_cookies(response: Response, token_response: TokenResponse) -> TokenResponse:
    """Attach authentication tokens as HttpOnly cookies and hide them from the JSON body."""
    settings = get_settings()
    cookie_options = {
        'httponly': True,
        'secure': settings.auth_cookie_secure,
        'samesite': settings.auth_cookie_samesite,
        'path': '/',
    }
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        token_response.access_token or '',
        max_age=token_response.expires_in,
        **cookie_options,
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token_response.refresh_token or '',
        max_age=60 * 60 * 24 * settings.refresh_token_expire_days,
        **cookie_options,
    )
    token_response.access_token = None
    token_response.refresh_token = None
    return token_response


def clear_auth_cookies(response: Response) -> None:
    """Expire authentication cookies for browser logout."""
    response.delete_cookie(ACCESS_COOKIE_NAME, path='/')
    response.delete_cookie(REFRESH_COOKIE_NAME, path='/')


@router.post('/login', response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    token_response = AuthService(db).login(
        email=payload.email,
        password=payload.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
    )
    return set_auth_cookies(response, token_response)


@router.post('/refresh', response_model=TokenResponse)
def refresh(
    response: Response,
    payload: RefreshRequest = Body(default_factory=RefreshRequest),
    refresh_token_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> TokenResponse:
    token_response = AuthService(db).refresh(refresh_token=payload.refresh_token or refresh_token_cookie or '')
    return set_auth_cookies(response, token_response)


@router.get('/me', response_model=TokenResponse)
def me(current_user=Depends(get_current_user)) -> TokenResponse:
    """Return the current session user without exposing token values."""
    return TokenResponse(
        expires_in=0,
        user={
            'id': str(current_user.id),
            'email': current_user.email,
            'full_name': current_user.full_name,
            'role': current_user.role.name,
            'must_reset_password': current_user.must_reset_password,
        },
    )


@router.post('/logout', response_model=MessageResponse)
def logout(
    payload: LogoutRequest,
    response: Response,
    refresh_token_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> MessageResponse:
    AuthService(db).logout(refresh_token=payload.refresh_token or refresh_token_cookie, user_id=current_user.id)
    clear_auth_cookies(response)
    return MessageResponse(message=AuthMessages.LOGOUT_SUCCESS)


@router.post('/forgot-password', response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    AuthService(db).request_password_reset(email=payload.email)
    return MessageResponse(message=AuthMessages.PASSWORD_RESET_SENT)


@router.post('/reset-password', response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    AuthService(db).reset_password(token=payload.token, new_password=payload.new_password)
    return MessageResponse(message=AuthMessages.PASSWORD_RESET_SUCCESS)
