from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import is_admin, is_operations_manager
from app.models.message_type import MessageClassification, MessageType
from app.models.user import User
from app.modules.config_management.service import ConfigService
from app.modules.pms.models import PMSDailyTaskEntry, PMSDayType, PMSFeedbackStatus
from app.modules.pms.schemas import PMSDailyEntryCreate, PMSDailyEntryResponse, PMSTaskLimits
from app.modules.sold_posting.models import SoldPostingLineItem


LIMIT_KEYS = {
    'sold_posting': 'pms.limit.sold_posting',
    'm2m_vip_followups': 'pms.limit.m2m_vip_followups',
    'tracking_sheet': 'pms.limit.tracking_sheet',
    'purchase_sheet': 'pms.limit.purchase_sheet',
    'booking': 'pms.limit.booking',
    'other_general_work': 'pms.limit.other_general_work',
}


class PMSService:
    def __init__(self, db: Session):
        self.db = db
        self.config = ConfigService(db)

    def limits(self) -> PMSTaskLimits:
        return PMSTaskLimits(**{name: self.config.get_int(key, getattr(PMSTaskLimits(), name)) for name, key in LIMIT_KEYS.items()})

    def draft(self, current_user, entry_date: date, user_id: UUID | None = None):
        target_user_id = self._target_user_id(current_user, user_id)
        existing = self._entry(target_user_id, entry_date)
        if existing:
            return existing, self.limits()
        return self._auto_entry(target_user_id, entry_date), self.limits()

    def save(self, current_user, payload: PMSDailyEntryCreate) -> PMSDailyTaskEntry:
        target_user_id = self._target_user_id(current_user, payload.user_id)
        user = self.db.get(User, target_user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
        values = payload.model_dump(exclude={'user_id'})
        try:
            values['day_type'] = PMSDayType(values['day_type'])
            values['feedback_status'] = PMSFeedbackStatus(values['feedback_status'])
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Invalid PMS dropdown value') from exc
        entry = self._entry(target_user_id, payload.entry_date)
        if entry:
            for key, value in values.items():
                setattr(entry, key, value)
        else:
            entry = PMSDailyTaskEntry(user_id=target_user_id, **values)
            self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def list_entries(self, current_user, *, date_from: date | None = None, date_to: date | None = None, user_id: UUID | None = None):
        statement = select(PMSDailyTaskEntry).options(joinedload(PMSDailyTaskEntry.user))
        if not self._can_view_all(current_user):
            statement = statement.where(PMSDailyTaskEntry.user_id == current_user.id)
        elif user_id:
            statement = statement.where(PMSDailyTaskEntry.user_id == user_id)
        if date_from:
            statement = statement.where(PMSDailyTaskEntry.entry_date >= date_from)
        if date_to:
            statement = statement.where(PMSDailyTaskEntry.entry_date <= date_to)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = list(self.db.scalars(statement.order_by(PMSDailyTaskEntry.entry_date.desc(), PMSDailyTaskEntry.created_at.desc())))
        return items, total

    def serialize(self, entry: PMSDailyTaskEntry) -> PMSDailyEntryResponse:
        return PMSDailyEntryResponse(
            id=entry.id,
            user_id=entry.user_id,
            user_name=(entry.user.full_name or entry.user.email) if entry.user else '',
            entry_date=entry.entry_date,
            day_type=entry.day_type.value,
            sold_posting_score=entry.sold_posting_score,
            m2m_vip_followups_score=entry.m2m_vip_followups_score,
            tracking_sheet_score=entry.tracking_sheet_score,
            purchase_sheet_score=entry.purchase_sheet_score,
            booking_score=entry.booking_score,
            other_general_work_score=entry.other_general_work_score,
            final_score_percent=entry.final_score_percent,
            sla_score=entry.sla_score,
            feedback_status=entry.feedback_status.value,
            particulars_error_note=entry.particulars_error_note,
            sla_remarks=entry.sla_remarks,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    def _auto_entry(self, user_id: UUID, entry_date: date):
        start = datetime.combine(entry_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        sold_count = self.db.scalar(
            select(func.count()).select_from(SoldPostingLineItem).where(
                SoldPostingLineItem.copied_by_user_id == user_id,
                SoldPostingLineItem.copied_at >= start,
                SoldPostingLineItem.copied_at < end,
            )
        ) or 0
        limits = self.limits()
        return PMSDailyTaskEntry(
            user_id=user_id,
            entry_date=entry_date,
            day_type=PMSDayType.WORKING_DAY,
            sold_posting_score=min(sold_count, limits.sold_posting),
            m2m_vip_followups_score=0,
            tracking_sheet_score=0,
            purchase_sheet_score=0,
            booking_score=0,
            other_general_work_score=0,
            final_score_percent=0,
            sla_score=20,
            feedback_status=PMSFeedbackStatus.GIVEN,
            particulars_error_note='NA',
            sla_remarks='NA',
        )

    def _classification_count(self, user_id: UUID, start: datetime, end: datetime, keywords: tuple[str, ...]) -> int:
        name = func.lower(MessageType.name)
        parent = MessageType.__table__.alias('parent_message_type')
        parent_name = func.lower(parent.c.name)
        conditions = [name.ilike(f'%{keyword}%') for keyword in keywords] + [parent_name.ilike(f'%{keyword}%') for keyword in keywords]
        statement = (
            select(func.count())
            .select_from(MessageClassification)
            .join(MessageType, MessageType.id == MessageClassification.message_type_id)
            .outerjoin(parent, parent.c.id == MessageType.parent_id)
            .where(MessageClassification.user_id == user_id, MessageClassification.created_at >= start, MessageClassification.created_at < end, or_(*conditions))
        )
        return int(self.db.scalar(statement) or 0)

    def _entry(self, user_id: UUID, entry_date: date):
        return self.db.scalar(select(PMSDailyTaskEntry).options(joinedload(PMSDailyTaskEntry.user)).where(PMSDailyTaskEntry.user_id == user_id, PMSDailyTaskEntry.entry_date == entry_date))

    def _target_user_id(self, current_user, requested: UUID | None) -> UUID:
        if requested and requested != current_user.id and not self._can_view_all(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You can only manage your own daily entries')
        return requested or current_user.id

    def _can_view_all(self, current_user) -> bool:
        return is_admin(current_user) or is_operations_manager(current_user)
