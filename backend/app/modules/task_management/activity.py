"""Counts for the shared main-task catalog."""

from datetime import UTC, date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.message_type import MessageClassification, MessageType
from app.modules.offer_management.models import OfferManagementEntry
from app.modules.sold_posting.models import SoldPostingLineItem
from app.modules.task_management.models import MainTask


INDIA_TIME = timezone(timedelta(hours=5, minutes=30))


def day_bounds(day: date):
    start = datetime.combine(day, time.min, tzinfo=INDIA_TIME).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=INDIA_TIME).astimezone(UTC)
    return start, end


def message_type_family(db: Session, root_id: UUID) -> set[UUID]:
    family = {root_id}
    frontier = {root_id}
    while frontier:
        children = set(db.scalars(select(MessageType.id).where(MessageType.parent_id.in_(frontier))))
        frontier = children - family
        family.update(frontier)
    return family


def count_main_task(db: Session, task: MainTask, user_id: UUID, day: date) -> int:
    start, end = day_bounds(day)
    if task.source_type == 'MESSAGE_TYPE' and task.message_type_id:
        return int(db.scalar(select(func.count()).select_from(MessageClassification).where(
            MessageClassification.user_id == user_id,
            MessageClassification.message_type_id.in_(message_type_family(db, task.message_type_id)),
            MessageClassification.created_at >= start,
            MessageClassification.created_at < end,
        )) or 0)
    if task.source_type == 'SOLD_POSTING':
        return int(db.scalar(select(func.count()).select_from(SoldPostingLineItem).where(
            SoldPostingLineItem.copied_by_user_id == user_id,
            SoldPostingLineItem.copied_at >= start,
            SoldPostingLineItem.copied_at < end,
        )) or 0)
    if task.source_type == 'OFFER_MANAGEMENT':
        return int(db.scalar(select(func.count()).select_from(OfferManagementEntry).where(
            OfferManagementEntry.created_by_user_id == user_id,
            OfferManagementEntry.offer_date == day,
        )) or 0)
    return 0


def count_main_task_after(db: Session, task: MainTask, user_id: UUID, since: datetime, day: date) -> int:
    """Count automatic task activity after a reviewed report snapshot."""
    _, end = day_bounds(day)
    if task.source_type == 'MESSAGE_TYPE' and task.message_type_id:
        return int(db.scalar(select(func.count()).select_from(MessageClassification).where(
            MessageClassification.user_id == user_id,
            MessageClassification.message_type_id.in_(message_type_family(db, task.message_type_id)),
            MessageClassification.created_at > since,
            MessageClassification.created_at < end,
        )) or 0)
    if task.source_type == 'SOLD_POSTING':
        return int(db.scalar(select(func.count()).select_from(SoldPostingLineItem).where(
            SoldPostingLineItem.copied_by_user_id == user_id,
            SoldPostingLineItem.copied_at > since,
            SoldPostingLineItem.copied_at < end,
        )) or 0)
    if task.source_type == 'OFFER_MANAGEMENT':
        return int(db.scalar(select(func.count()).select_from(OfferManagementEntry).where(
            OfferManagementEntry.created_by_user_id == user_id,
            OfferManagementEntry.created_at > since,
            OfferManagementEntry.created_at < end,
        )) or 0)
    return 0


def active_main_tasks(db: Session) -> list[MainTask]:
    return list(db.scalars(select(MainTask).where(MainTask.is_active.is_(True)).order_by(MainTask.created_at, MainTask.name)))
