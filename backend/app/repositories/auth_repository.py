from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.audit_log import AuditLog
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User


class AuthRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_email(self, email: str) -> User | None:
        statement = (
            select(User)
            .options(joinedload(User.role))
            .where(User.email == email.lower().strip())
        )
        return self.db.scalar(statement)

    def get_user_by_id(self, user_id: UUID) -> User | None:
        statement = select(User).options(joinedload(User.role)).where(User.id == user_id)
        return self.db.scalar(statement)

    def store_refresh_token(self, *, user_id: UUID, token_hash: str, jwt_id: str, expires_at: datetime) -> None:
        self.db.add(
            RefreshToken(
                user_id=user_id,
                token_hash=token_hash,
                jwt_id=jwt_id,
                expires_at=expires_at,
            )
        )

    def get_active_refresh_token(self, token_hash: str) -> RefreshToken | None:
        statement = (
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .where(RefreshToken.revoked_at.is_(None))
            .where(RefreshToken.expires_at > datetime.now(UTC))
        )
        return self.db.scalar(statement)

    def revoke_refresh_token(self, token: RefreshToken) -> None:
        token.revoked_at = datetime.now(UTC)

    def revoke_all_user_refresh_tokens(self, user_id: UUID) -> None:
        statement = (
            select(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .where(RefreshToken.revoked_at.is_(None))
        )
        for token in self.db.scalars(statement):
            token.revoked_at = datetime.now(UTC)

    def store_password_reset_token(self, *, user_id: UUID, token_hash: str, expires_at: datetime) -> None:
        self.db.add(
            PasswordResetToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )

    def get_active_password_reset_token(self, token_hash: str) -> PasswordResetToken | None:
        statement = (
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == token_hash)
            .where(PasswordResetToken.used_at.is_(None))
            .where(PasswordResetToken.expires_at > datetime.now(UTC))
        )
        return self.db.scalar(statement)

    def mark_password_reset_token_used(self, token: PasswordResetToken) -> None:
        token.used_at = datetime.now(UTC)

    def add_audit_log(
        self,
        *,
        action: str,
        user_id: UUID | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.db.add(
            AuditLog(
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
