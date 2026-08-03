from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import is_admin
from app.models.conversation import ConversationSLAHistory
from app.models.message_type import MessageClassification, MessageType
from app.models.user import User
from app.modules.pms.models import PMSDailyTaskEntry, PMSDailyTaskEntryHistory, PMSDayType, PMSErrorLevel, PMSFeedbackStatus
from app.modules.pms.schemas import PMSDailyEntryCreate, PMSDailyEntryResponse, PMSScoreItem, PMSTaskLimits
from app.modules.sold_posting.models import SoldPostingLineItem
from app.modules.task_management.models import Subtask, SubtaskSourceType, TaskCategory, TaskStatus, UserSubtaskAssignment


class PMSService:
    def __init__(self, db: Session):
        self.db = db

    def limits(self) -> PMSTaskLimits:
        return PMSTaskLimits()

    def draft(self, current_user, entry_date: date, user_id: UUID | None = None):
        self._require_admin(current_user)
        if not user_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='User is required before fetching Daily Entry data')
        existing = self._entry(user_id, entry_date)
        if existing:
            return existing, self.limits()
        return self._auto_entry(user_id, entry_date), self.limits()

    def save(self, current_user, payload: PMSDailyEntryCreate) -> PMSDailyTaskEntry:
        self._require_admin(current_user)
        if not payload.user_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='User is required')
        target_user_id = payload.user_id
        user = self.db.get(User, target_user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
        if payload.error_level in {'MINOR', 'MAJOR'} and not (payload.error_remark or '').strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Error Remark is required for Minor or Major errors')

        score_items = [item.model_dump(mode='json') for item in payload.score_items]
        if payload.error_level == 'MAJOR':
            score_items = [{**item, 'value': 0} for item in score_items]
        final_score = self.calculate_final(score_items, payload.sla_score, payload.error_level)

        values = payload.model_dump(exclude={'user_id', 'score_items', 'final_score_percent'})
        try:
            values['day_type'] = PMSDayType(values['day_type'])
            values['feedback_status'] = PMSFeedbackStatus(values['feedback_status'])
            values['error_level'] = PMSErrorLevel(values['error_level'])
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Invalid PMS dropdown value') from exc
        values['score_items'] = score_items
        values['final_score_percent'] = final_score
        if values['error_level'] == PMSErrorLevel.MAJOR:
            values['sla_score'] = 0

        entry = self._entry(target_user_id, payload.entry_date)
        action = 'UPDATED' if entry else 'CREATED'
        if entry:
            for key, value in values.items():
                setattr(entry, key, value)
            entry.updated_by_user_id = current_user.id
        else:
            entry = PMSDailyTaskEntry(user_id=target_user_id, created_by_user_id=current_user.id, updated_by_user_id=current_user.id, **values)
            self.db.add(entry)
            self.db.flush()
        self.db.add(PMSDailyTaskEntryHistory(entry_id=entry.id, changed_by_user_id=current_user.id, action=action, snapshot=self._snapshot(entry)))
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def list_entries(self, current_user, *, date_from: date | None = None, date_to: date | None = None, user_id: UUID | None = None):
        statement = select(PMSDailyTaskEntry).options(joinedload(PMSDailyTaskEntry.user), joinedload(PMSDailyTaskEntry.created_by), joinedload(PMSDailyTaskEntry.updated_by))
        if not is_admin(current_user):
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
            score_items=[PMSScoreItem(**item) for item in (entry.score_items or [])],
            error_level=entry.error_level.value,
            error_remark=entry.error_remark,
            feedback_status=entry.feedback_status.value,
            particulars_error_note=entry.particulars_error_note,
            sla_remarks=entry.sla_remarks,
            created_by_user_id=entry.created_by_user_id,
            updated_by_user_id=entry.updated_by_user_id,
            created_by_name=(entry.created_by.full_name or entry.created_by.email) if entry.created_by else None,
            updated_by_name=(entry.updated_by.full_name or entry.updated_by.email) if entry.updated_by else None,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    def calculate_final(self, score_items: list[dict], sla_score: int, error_level: str) -> int:
        if error_level == 'MAJOR':
            return 0
        applicable = [item for item in score_items if item.get('status') != 'NOT_APPLICABLE' and (item.get('status') == 'ENTERED' or int(item.get('value') or 0) > 0)]
        earned = sum(min(int(item.get('value') or 0), int(item.get('max_score') or 1)) for item in applicable)
        possible = sum(int(item.get('max_score') or 1) for item in applicable)
        if sla_score is not None:
            earned += max(0, min(int(sla_score or 0), 20))
            possible += 20
        return round((earned / possible) * 100) if possible else 0

    def _auto_entry(self, user_id: UUID, entry_date: date):
        start = datetime.combine(entry_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        items = self._assigned_task_items(user_id, entry_date, start, end)
        sla_score = self._sla_score(user_id, start, end)
        return PMSDailyTaskEntry(
            user_id=user_id,
            entry_date=entry_date,
            day_type=PMSDayType.WORKING_DAY,
            score_items=items,
            final_score_percent=0,
            sla_score=sla_score,
            feedback_status=PMSFeedbackStatus.GIVEN,
            error_level=PMSErrorLevel.NO_ERROR,
            particulars_error_note='NA',
            sla_remarks='NA',
        )

    def _assigned_task_items(self, user_id: UUID, entry_date: date, start: datetime, end: datetime) -> list[dict]:
        assignments = list(self.db.scalars(
            select(UserSubtaskAssignment)
            .join(UserSubtaskAssignment.subtask)
            .join(Subtask.category)
            .where(
                UserSubtaskAssignment.user_id == user_id,
                UserSubtaskAssignment.status == TaskStatus.ACTIVE,
                UserSubtaskAssignment.effective_from <= entry_date,
                ((UserSubtaskAssignment.effective_to.is_(None)) | (UserSubtaskAssignment.effective_to >= entry_date)),
                Subtask.status == TaskStatus.ACTIVE,
                TaskCategory.status == TaskStatus.ACTIVE,
            )
            .order_by(UserSubtaskAssignment.display_order, Subtask.display_order, Subtask.name)
        ))
        return [self._assignment_item(assignment, user_id, start, end) for assignment in assignments]

    def _assignment_item(self, assignment: UserSubtaskAssignment, user_id: UUID, start: datetime, end: datetime) -> dict:
        subtask = assignment.subtask
        max_score = max(1, round(float(assignment.quality_weight or 0)))
        label = f'{subtask.category.name} - {subtask.name}' if subtask.category else subtask.name
        source = 'AUTO' if assignment.auto_fetch_enabled and subtask.supports_automatic_fetch else 'MANUAL'
        value = 0
        status_value = 'NOT_ENTERED'
        if source == 'AUTO':
            value = self._automatic_count(subtask, user_id, start, end)
            status_value = 'ENTERED' if value > 0 else 'NOT_APPLICABLE'
        return self._item(
            f'assignment:{assignment.id}',
            label,
            min(value, max_score),
            max_score,
            source,
            status=status_value,
            message_type_id=subtask.source_reference_id if subtask.source_type == SubtaskSourceType.MESSAGE_CATEGORY else None,
        )

    def _automatic_count(self, subtask: Subtask, user_id: UUID, start: datetime, end: datetime) -> int:
        if subtask.source_type == SubtaskSourceType.MESSAGE_CATEGORY and subtask.source_reference_id:
            return int(self.db.scalar(
                select(func.count())
                .select_from(MessageClassification)
                .where(
                    MessageClassification.user_id == user_id,
                    MessageClassification.message_type_id == subtask.source_reference_id,
                    MessageClassification.created_at >= start,
                    MessageClassification.created_at < end,
                )
            ) or 0)
        if subtask.source_type == SubtaskSourceType.SOLD_POSTING:
            return int(self.db.scalar(
                select(func.count())
                .select_from(SoldPostingLineItem)
                .where(
                    SoldPostingLineItem.copied_by_user_id == user_id,
                    SoldPostingLineItem.copied_at >= start,
                    SoldPostingLineItem.copied_at < end,
                )
            ) or 0)
        return 0

    def _sla_score(self, user_id: UUID, start: datetime, end: datetime) -> int:
        rows = list(self.db.scalars(select(ConversationSLAHistory).where(ConversationSLAHistory.replied_by == user_id, ConversationSLAHistory.replied_time >= start, ConversationSLAHistory.replied_time < end)))
        if not rows:
            return 0
        met = sum(1 for row in rows if row.sla_met)
        return round((met / len(rows)) * 20)

    def _item(self, key: str, label: str, value: int, max_score: int, source: str, *, status: str | None = None, message_type_id: UUID | None = None) -> dict:
        return {'key': key, 'label': label, 'value': value, 'max_score': max_score, 'status': status or ('ENTERED' if value > 0 else 'NOT_ENTERED'), 'source': source, 'message_type_id': str(message_type_id) if message_type_id else None}

    def _snapshot(self, entry: PMSDailyTaskEntry) -> dict:
        return {'entry_date': entry.entry_date.isoformat(), 'score_items': entry.score_items, 'final_score_percent': entry.final_score_percent, 'sla_score': entry.sla_score, 'error_level': entry.error_level.value, 'error_remark': entry.error_remark}

    def _entry(self, user_id: UUID, entry_date: date):
        return self.db.scalar(select(PMSDailyTaskEntry).options(joinedload(PMSDailyTaskEntry.user), joinedload(PMSDailyTaskEntry.created_by), joinedload(PMSDailyTaskEntry.updated_by)).where(PMSDailyTaskEntry.user_id == user_id, PMSDailyTaskEntry.entry_date == entry_date))

    def _require_admin(self, current_user) -> None:
        if not is_admin(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins can create or edit Daily Entry records')
