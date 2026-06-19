from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: UUID
    title: str
    body: str
    event_type: str
    resource_type: str | None
    resource_id: UUID | None
    is_read: bool
    created_at: datetime
    read_at: datetime | None


class NotificationPageResponse(BaseModel):
    items: list[NotificationResponse]
    unread_count: int
    total: int
    limit: int
    offset: int
