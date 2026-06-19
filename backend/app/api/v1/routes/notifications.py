from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.notification import Notification
from app.schemas.notification import NotificationPageResponse, NotificationResponse
from app.services.notification_service import NotificationService


router = APIRouter()


def serialize_notification(notification: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        title=notification.title,
        body=notification.body,
        event_type=notification.event_type,
        resource_type=notification.resource_type,
        resource_id=notification.resource_id,
        is_read=notification.is_read,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


@router.get('', response_model=NotificationPageResponse)
def list_notifications(
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    unread_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> NotificationPageResponse:
    items, total, unread_count = NotificationService(db).list_for_user(
        current_user.id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )
    return NotificationPageResponse(
        items=[serialize_notification(item) for item in items],
        unread_count=unread_count,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch('/read')
def mark_all_read(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, int]:
    updated_count = NotificationService(db).mark_read(current_user.id)
    db.commit()
    return {'updated_count': updated_count}


@router.patch('/{notification_id}/read')
def mark_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, int]:
    updated_count = NotificationService(db).mark_read(current_user.id, notification_id)
    db.commit()
    return {'updated_count': updated_count}
