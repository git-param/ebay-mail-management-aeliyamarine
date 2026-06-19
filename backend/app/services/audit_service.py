from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def audit_category_for_action(action: str) -> str:
    prefix = action.split('_', 1)[0]
    if prefix in {'LOGIN', 'LOGOUT', 'PASSWORD'}:
        return 'AUTHENTICATION'
    if prefix == 'USER':
        return 'USER_MANAGEMENT'
    if prefix == 'CATEGORY':
        return 'CATEGORY_MANAGEMENT'
    if prefix in {'CONVERSATION', 'MESSAGE', 'BULK'}:
        return 'ASSIGNMENT' if 'ASSIGN' in action else 'MESSAGE_MANAGEMENT'
    if prefix == 'EBAY':
        return 'EBAY'
    if prefix == 'SYNC':
        return 'SYNC'
    if prefix == 'NOTIFICATION':
        return 'NOTIFICATION'
    return 'SYSTEM'


class AuditService:
    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        *,
        action: str,
        user_id: UUID | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        category: str | None = None,
        status: str = 'SUCCESS',
        metadata: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            category=category or audit_category_for_action(action),
            status=status,
            audit_metadata=metadata,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(audit_log)
        return audit_log
