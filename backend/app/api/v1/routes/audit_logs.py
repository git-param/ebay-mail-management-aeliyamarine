from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import require_admin
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User
from app.schemas.audit import AuditLogPageResponse, AuditLogResponse, AuditUserResponse


router = APIRouter()

ACTION_LABELS = {
    'LOGIN_SUCCESS': 'User Logged In',
    'MESSAGE_TYPE_CREATED': 'Created New Message Type',
    'MESSAGE_STATUS_CHANGED': 'Conversation Status Updated',
    'CONVERSATION_ASSIGNED': 'Assigned Conversation',
    'MESSAGE_REPLY_SENT': 'Replied to Buyer',
}
MODULE_LABELS = {
    'AUTHENTICATION': 'Authentication', 'ASSIGNMENT': 'Inbox',
    'MESSAGE_MANAGEMENT': 'Messaging', 'CATEGORY_MANAGEMENT': 'Categories',
    'USER_MANAGEMENT': 'Users', 'EBAY': 'eBay', 'SYNC': 'Synchronization',
}


def serialize_user(user: User | None) -> AuditUserResponse | None:
    if not user:
        return None
    return AuditUserResponse(
        id=user.id,
        name=user.full_name,
        email=user.email,
        role=user.role.name if user.role else '',
    )


def serialize_audit_log(log: AuditLog) -> AuditLogResponse:
    """Translate a technical audit row into a manager-readable activity event."""
    metadata = log.audit_metadata or {}
    details = ', '.join(f'{key.replace("_", " ").title()}: {value}' for key, value in metadata.items()) or 'No additional details'
    resource_name = (log.entity_type or 'Activity').replace('_', ' ').title()
    return AuditLogResponse(
        id=log.id,
        user_id=log.user_id,
        user=serialize_user(log.user),
        action=log.action,
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        category=log.category,
        status=log.status,
        metadata=log.audit_metadata,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        created_at=log.created_at,
        action_label=ACTION_LABELS.get(log.action, log.action.replace('_', ' ').title()),
        module_label=MODULE_LABELS.get(log.category or '', (log.category or 'System').replace('_', ' ').title()),
        resource_label=f'{resource_name} #{str(log.entity_id)[:8]}' if log.entity_id else resource_name,
        details=details,
    )


def filtered_statement(
    *,
    user_id: UUID | None = None,
    role: str | None = None,
    category: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
):
    statement = select(AuditLog).options(joinedload(AuditLog.user).joinedload(User.role))
    if role:
        statement = statement.join(AuditLog.user).join(User.role).where(func.lower(Role.name) == role.lower())
    if user_id:
        statement = statement.where(AuditLog.user_id == user_id)
    if category:
        statement = statement.where(AuditLog.category == category)
    if action:
        statement = statement.where(AuditLog.action == action)
    if entity_type:
        statement = statement.where(AuditLog.entity_type == entity_type)
    if status:
        statement = statement.where(AuditLog.status == status)
    if start_date:
        statement = statement.where(AuditLog.created_at >= start_date)
    if end_date:
        statement = statement.where(AuditLog.created_at <= end_date)
    return statement


@router.get('', response_model=AuditLogPageResponse)
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user_id: UUID | None = Query(default=None),
    role: str | None = Query(default=None),
    category: str | None = Query(default=None),
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> AuditLogPageResponse:
    statement = filtered_statement(
        user_id=user_id,
        role=role,
        category=category,
        action=action,
        entity_type=entity_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = list(db.scalars(statement.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)))
    return AuditLogPageResponse(items=[serialize_audit_log(item) for item in items], total=total, limit=limit, offset=offset)


@router.get('/export')
def export_audit_logs(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> Response:
    rows = list(db.scalars(select(AuditLog).options(joinedload(AuditLog.user)).order_by(AuditLog.created_at.desc()).limit(5000)))
    content = 'created_at,user_email,action,category,status,entity_type,entity_id\n'
    for row in rows:
        content += f'{row.created_at},{row.user.email if row.user else ""},{row.action},{row.category or ""},{row.status or ""},{row.entity_type or ""},{row.entity_id or ""}\n'
    return Response(content=content, media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="audit_logs.csv"'})
