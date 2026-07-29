from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.notification import Notification


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        user_id: UUID,
        title: str,
        body: str,
        event_type: str,
        event_key: str,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        metadata: dict | None = None,
    ) -> Notification | None:
        existing = self.db.scalar(
            select(Notification)
            .where(Notification.user_id == user_id)
            .where(Notification.event_key == event_key)
        )
        if existing:
            return None
        notification = Notification(
            user_id=user_id,
            title=title[:160],
            body=body,
            event_type=event_type,
            event_key=event_key,
            resource_type=resource_type,
            resource_id=resource_id,
            notification_metadata=metadata,
        )
        self.db.add(notification)
        self.db.flush()
        return notification

    def list_for_user(self, user_id: UUID, *, limit: int, offset: int, unread_only: bool = False) -> tuple[list[Notification], int, int]:
        statement = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            statement = statement.where(Notification.is_read.is_(False))
        total = int(self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        unread_count = int(
            self.db.scalar(
                select(func.count(Notification.id))
                .where(Notification.user_id == user_id)
                .where(Notification.is_read.is_(False))
            )
            or 0
        )
        items = list(
            self.db.scalars(
                statement.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
            )
        )
        return items, total, unread_count

    def mark_read(self, user_id: UUID, notification_id: UUID | None = None) -> int:
        statement = select(Notification).where(Notification.user_id == user_id).where(Notification.is_read.is_(False))
        if notification_id:
            statement = statement.where(Notification.id == notification_id)
        items = list(self.db.scalars(statement))
        for item in items:
            item.is_read = True
            item.read_at = datetime.now(UTC)
        return len(items)

    def delete_for_user(self, user_id: UUID, notification_id: UUID | None = None) -> int:
        statement = delete(Notification).where(Notification.user_id == user_id)
        if notification_id:
            statement = statement.where(Notification.id == notification_id)
        result = self.db.execute(statement)
        return int(result.rowcount or 0)

    def delete_older_than(self, cutoff: datetime) -> int:
        result = self.db.execute(delete(Notification).where(Notification.created_at < cutoff))
        return int(result.rowcount or 0)
