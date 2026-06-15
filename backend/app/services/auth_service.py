from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.constants.auth_constants import AuditActions, AuthMessages
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_url_safe_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import TokenResponse, UserSession
from app.services.email_service import EmailService
from app.utils.auth_utils import ensure_new_password_is_valid


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AuthRepository(db)
        self.email_service = EmailService()
        self.settings = get_settings()

    def login(self, *, email: str, password: str, ip_address: str | None, user_agent: str | None) -> TokenResponse:
        user = self.repository.get_user_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            self.repository.add_audit_log(
                action=AuditActions.LOGIN_FAILURE,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthMessages.INVALID_LOGIN)

        if not user.is_active:
            self.repository.add_audit_log(
                action=AuditActions.LOGIN_BLOCKED_INACTIVE_USER,
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=AuthMessages.INACTIVE_USER)

        access_token, _, access_expires_at = create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role.name,
        )
        refresh_token, refresh_jti, refresh_expires_at = create_refresh_token(user_id=str(user.id))

        self.repository.store_refresh_token(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            jwt_id=refresh_jti,
            expires_at=refresh_expires_at,
        )
        self.repository.add_audit_log(
            action=AuditActions.LOGIN_SUCCESS,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.commit()

        return self._build_token_response(
            user=user,
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=access_expires_at,
        )

    def refresh(self, *, refresh_token: str) -> TokenResponse:
        payload = self._decode_refresh_payload(refresh_token)
        stored_token = self.repository.get_active_refresh_token(hash_token(refresh_token))

        if not stored_token or stored_token.jwt_id != payload.get('jti'):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthMessages.INVALID_REFRESH_TOKEN)

        user = self.repository.get_user_by_id(UUID(payload['sub']))
        if not user or not user.is_active:
            if stored_token:
                self.repository.revoke_refresh_token(stored_token)
                self.db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthMessages.INVALID_REFRESH_TOKEN)

        self.repository.revoke_refresh_token(stored_token)
        access_token, _, access_expires_at = create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role.name,
        )
        new_refresh_token, refresh_jti, refresh_expires_at = create_refresh_token(user_id=str(user.id))
        self.repository.store_refresh_token(
            user_id=user.id,
            token_hash=hash_token(new_refresh_token),
            jwt_id=refresh_jti,
            expires_at=refresh_expires_at,
        )
        self.db.commit()

        return self._build_token_response(
            user=user,
            access_token=access_token,
            refresh_token=new_refresh_token,
            access_expires_at=access_expires_at,
        )

    def logout(self, *, refresh_token: str | None, user_id: UUID | None = None) -> None:
        if refresh_token:
            stored_token = self.repository.get_active_refresh_token(hash_token(refresh_token))
            if stored_token:
                self.repository.revoke_refresh_token(stored_token)
                user_id = stored_token.user_id
        elif user_id:
            self.repository.revoke_all_user_refresh_tokens(user_id)

        self.repository.add_audit_log(action=AuditActions.LOGOUT, user_id=user_id)
        self.db.commit()

    def request_password_reset(self, *, email: str) -> None:
        user = self.repository.get_user_by_email(email)
        if user and user.is_active:
            raw_token = create_url_safe_token()
            expires_at = datetime.now(UTC) + timedelta(minutes=self.settings.password_reset_token_expire_minutes)
            self.repository.store_password_reset_token(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                expires_at=expires_at,
            )
            reset_link = self.email_service.build_password_reset_link(raw_token)
            self.email_service.send_password_reset_email(email=user.email, reset_link=reset_link)
            self.repository.add_audit_log(action=AuditActions.PASSWORD_RESET_REQUESTED, user_id=user.id)
            self.db.commit()

    def reset_password(self, *, token: str, new_password: str) -> None:
        reset_token = self.repository.get_active_password_reset_token(hash_token(token))
        if not reset_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=AuthMessages.INVALID_RESET_TOKEN)

        user = self.repository.get_user_by_id(reset_token.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=AuthMessages.INVALID_RESET_TOKEN)

        ensure_new_password_is_valid(new_password=new_password, current_password_hash=user.password_hash)
        user.password_hash = hash_password(new_password)
        user.must_reset_password = False
        self.repository.mark_password_reset_token_used(reset_token)
        self.repository.revoke_all_user_refresh_tokens(user.id)
        self.repository.add_audit_log(action=AuditActions.PASSWORD_RESET_COMPLETED, user_id=user.id)
        self.db.commit()

    def _decode_refresh_payload(self, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthMessages.INVALID_REFRESH_TOKEN) from exc

        if payload.get('type') != 'refresh' or not payload.get('sub') or not payload.get('jti'):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthMessages.INVALID_REFRESH_TOKEN)
        return payload

    def _build_token_response(self, *, user, access_token: str, refresh_token: str, access_expires_at: datetime) -> TokenResponse:
        seconds_until_expiry = int((access_expires_at - datetime.now(UTC)).total_seconds())
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=max(seconds_until_expiry, 0),
            user=UserSession(
                id=str(user.id),
                email=user.email,
                full_name=user.full_name,
                role=user.role.name,
                must_reset_password=user.must_reset_password,
            ),
        )
