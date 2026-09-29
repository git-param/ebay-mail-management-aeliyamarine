from datetime import date, datetime, time, timedelta
import csv
from io import StringIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.constants.api import AuditLogsRoutes
from app.api.dependencies import require_admin
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User
from app.schemas.audit import AuditLogDeleteRequest, AuditLogPageResponse, AuditLogResponse, AuditUserResponse
from app.services.audit_service import AuditService, audit_category_for_action
from app.services.audit_presentation_service import AuditPresentationService
from app.services.daily_login_service import INDIA_TIME, audit_date_bounds


router = APIRouter()

ACTION_LABELS = {
    'LOGIN_SUCCESS': 'User Logged In',
    'MESSAGE_TYPE_CREATED': 'Created New Message Type',
    'MESSAGE_STATUS_CHANGED': 'Conversation Status Updated',
    'CONVERSATION_ASSIGNED': 'Assigned Conversation',
    'MESSAGE_REPLY_SENT': 'Replied to Buyer',
    'MESSAGE_CATEGORY_CHANGED': 'Changed Message Category',
    'CONVERSATION_UNASSIGNED': 'Unassigned Conversation',
    'REPLY_CATEGORIZED': 'Categorized Reply',
    'INTERNAL_NOTE_CREATED': 'Created Internal Note',
    'AUDIT_LOGS_DELETED': 'Deleted Audit Logs',
}
MODULE_LABELS = {
    'AUTHENTICATION': 'Authentication', 'ASSIGNMENT': 'Inbox',
    'MESSAGE_MANAGEMENT': 'Messaging', 'CATEGORY_MANAGEMENT': 'Categories',
    'USER_MANAGEMENT': 'Users', 'EBAY': 'eBay', 'SYNC': 'Synchronization',
    'BREAK_MANAGEMENT': 'Break Management', 'LEAVE_MANAGEMENT': 'Leave Management',
    'PMS_MANAGEMENT': 'PMS', 'TASK_MANAGEMENT': 'Task Management',
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


def serialize_audit_log(log: AuditLog, presenter=None) -> AuditLogResponse:
    """Translate a technical audit row into a manager-readable activity event."""
    metadata = presenter.enrich(action=log.action, user_id=log.user_id, entity_type=log.entity_type,
        entity_id=log.entity_id, metadata=log.audit_metadata, created_at=log.created_at) if presenter else (log.audit_metadata or {})
    actor = metadata.get('actor_name') or (log.user.full_name if log.user else 'System')
    details = metadata.get('description') or AuditPresentationService.describe(log.action, {**metadata, 'actor_name': actor})
    resource_name = (log.entity_type or 'Activity').replace('_', ' ').title()
    category = log.category or audit_category_for_action(log.action)
    return AuditLogResponse(
        id=log.id,
        user_id=log.user_id,
        user=serialize_user(log.user),
        action=log.action,
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        category=category,
        status=log.status,
        metadata=log.audit_metadata,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        created_at=log.created_at,
        action_label=ACTION_LABELS.get(log.action, log.action.replace('_', ' ').title()),
        module_label=MODULE_LABELS.get(category, category.replace('_', ' ').title()),
        resource_label=metadata.get('resource_label') or resource_name,
        actor_name=actor,
        conversation_id=metadata.get('conversation_id'),
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
        statement = statement.where(AuditLog.created_at < end_date)
    return statement


@router.get(AuditLogsRoutes.FILTERS)
def audit_filter_options(db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return {
        key: [value for value in db.scalars(select(column).distinct().order_by(column)) if value]
        for key, column in {
            'categories': AuditLog.category,
            'actions': AuditLog.action,
            'statuses': AuditLog.status,
            'entity_types': AuditLog.entity_type,
        }.items()
    }


@router.get(AuditLogsRoutes.ROOT, response_model=AuditLogPageResponse)
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
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> AuditLogPageResponse:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, 'From date must be on or before To date')
    statement = filtered_statement(
        user_id=user_id,
        role=role,
        category=category,
        action=action,
        entity_type=entity_type,
        status=status,
        start_date=datetime.combine(date_from, time.min, tzinfo=INDIA_TIME) if date_from else start_date,
        end_date=datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=INDIA_TIME) if date_to else end_date,
    )
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = list(db.scalars(statement.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)))
    presenter = AuditPresentationService(db)
    presenter.preload(items)
    return AuditLogPageResponse(items=[serialize_audit_log(item, presenter) for item in items], total=total, limit=limit, offset=offset)


@router.get(AuditLogsRoutes.EXPORT)
def export_audit_logs(
    category: str | None = Query(default=None),
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> Response:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, 'From date must be on or before To date')
    statement = filtered_statement(
        category=category, action=action, entity_type=entity_type, status=status,
        start_date=datetime.combine(date_from, time.min, tzinfo=INDIA_TIME) if date_from else None,
        end_date=datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=INDIA_TIME) if date_to else None,
    )
    rows = list(db.scalars(statement.order_by(AuditLog.created_at.desc()).limit(5000)))
    presenter = AuditPresentationService(db)
    presenter.preload(rows)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date (UTC)', 'User', 'Role', 'Action', 'Module', 'Resource', 'Status', 'Details'])
    for row in rows:
        item = serialize_audit_log(row, presenter)
        writer.writerow([row.created_at, item.actor_name, (row.audit_metadata or {}).get('actor_role') or (item.user.role if item.user else ''), item.action_label, item.module_label, item.resource_label, item.status, item.details])
    return Response(content=output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="audit_logs.csv"'})


def deletion_criteria(date_from, date_to):
    start, end = audit_date_bounds(date_from, date_to)
    return (AuditLog.created_at >= start, AuditLog.created_at < end)


@router.get(AuditLogsRoutes.DELETION_PREVIEW)
def preview_audit_deletion(date_from: date, date_to: date, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    count = db.scalar(select(func.count()).select_from(AuditLog).where(*deletion_criteria(date_from, date_to)))
    return {'count': count or 0, 'timezone': 'Asia/Kolkata'}


@router.delete(AuditLogsRoutes.ROOT)
def delete_audit_logs(payload: AuditLogDeleteRequest, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    if payload.confirmation != 'DELETE AUDIT LOGS':
        raise HTTPException(422, 'Type DELETE AUDIT LOGS to confirm')
    result = db.execute(delete(AuditLog).where(*deletion_criteria(payload.date_from, payload.date_to)))
    count = result.rowcount
    AuditService(db).log(action='AUDIT_LOGS_DELETED', user_id=current_user.id, category='SYSTEM',
        metadata={'date_from': payload.date_from.isoformat(), 'date_to': payload.date_to.isoformat(), 'deleted_count': count})
    db.commit()
    return {'deleted_count': count}
