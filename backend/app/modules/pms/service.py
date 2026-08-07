from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import is_admin
from app.models.message_type import MessageClassification, MessageType
from app.models.user import User
from app.modules.offer_management.models import OfferManagementEntry
from app.modules.pms.models import PMSDailyTaskEntry, PMSDailyTaskEntryHistory, PMSDayType, PMSErrorLevel, PMSFeedbackStatus
from app.modules.pms.schemas import (
    PMSDailyEntryCreate,
    PMSDailyEntryResponse,
    PMSLoadRequestUser,
    PMSLoadResponseItem,
    PMSScoreItem,
    PMSTaskLimits,
    PMSUploadEntry,
    PMSUploadResultItem,
)
from app.modules.sold_posting.models import SoldPostingLineItem
from app.modules.task_management.models import Subtask, SubtaskSourceType, TaskCategory, TaskStatus, UserSubtaskAssignment


class PMSService:
    SLA_MAX = 20

    def __init__(self, db: Session):
        self.db = db

    def limits(self) -> PMSTaskLimits:
        return PMSTaskLimits(sla_max=self.SLA_MAX)

    # ------------------------------------------------------------------
    # Single-user draft (kept for backward compatibility with existing
    # single-user callers of GET /pms/draft)
    # ------------------------------------------------------------------
    def draft(self, current_user, entry_date: date, user_id: UUID | None = None):
        self._require_admin(current_user)
        if not user_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='User is required before fetching Daily Entry data')
        user = self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
        existing = self._entry(user_id, entry_date)
        if existing:
            return existing, self.limits()
        return self._auto_entry(user_id, entry_date), self.limits()

    # ------------------------------------------------------------------
    # Multi-user load: all active agents, or one selected agent
    # ------------------------------------------------------------------
    def load(self, current_user, entry_date: date, user_id: UUID | None = None) -> list[PMSLoadResponseItem]:
        self._require_admin(current_user)
        users = self._target_users(user_id)
        items: list[PMSLoadResponseItem] = []
        for user in users:
            existing = self._entry(user.id, entry_date)
            entry = existing if existing else self._auto_entry(user.id, entry_date)
            items.append(PMSLoadResponseItem(
                user=PMSLoadRequestUser(id=user.id, full_name=user.full_name, email=user.email),
                entry=self._to_base_schema(entry),
                existing_entry_id=existing.id if existing else None,
            ))
        return items
    
    def _target_users(self, user_id: UUID | None) -> list[User]:
        if user_id:
            user = self.db.get(User, user_id)

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )

            if not self._is_agent(user):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Daily Task Entry can only be loaded for Agent users",
                )

            return [user]

        statement = (
            select(User)
            .where(
                User.is_active.is_(True),
                User.role.has(name="Support Agent"),
            )
            .order_by(User.full_name.asc())
        )

        return list(self.db.scalars(statement).all())
    
    def _to_base_schema(self, entry: PMSDailyTaskEntry) -> dict:
        return {
            'entry_date': entry.entry_date,
            'day_type': entry.day_type.value,
            'final_score_percent': entry.final_score_percent or 0,
            'sla_score': entry.sla_score or 0,
            'score_items': entry.score_items or [],
            'error_level': entry.error_level.value,
            'error_remark': entry.error_remark,
            'remarks': entry.remarks,
            'particulars_error_note': entry.particulars_error_note,
            'sla_remarks': entry.sla_remarks,
        }

    # ------------------------------------------------------------------
    # Single-entry save (kept for backward compatibility)
    # ------------------------------------------------------------------
    def save(self, current_user, payload: PMSDailyEntryCreate) -> PMSDailyTaskEntry:
        self._require_admin(current_user)
        entry, _ = self._save_one(current_user, payload)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    # ------------------------------------------------------------------
    # Bulk upload: create-or-update per user/date, one DB transaction,
    # per-user success/failure reporting.
    # ------------------------------------------------------------------
    def upload(self, current_user, entries: list[PMSUploadEntry]) -> list[PMSUploadResultItem]:
        self._require_admin(current_user)
        results: list[PMSUploadResultItem] = []
        for payload in entries:
            try:
                with self.db.begin_nested():
                    entry, _ = self._save_one(current_user, payload)
                    self.db.flush()
                results.append(PMSUploadResultItem(user_id=payload.user_id, success=True, entry_id=entry.id))
            except HTTPException as exc:
                results.append(PMSUploadResultItem(user_id=payload.user_id, success=False, error=str(exc.detail)))
            except Exception as exc:  # noqa: BLE001 - surface to caller per-row instead of failing the whole batch
                results.append(PMSUploadResultItem(user_id=payload.user_id, success=False, error=str(exc)))
        self.db.commit()
        return results

    def _save_one(self, current_user, payload: PMSDailyEntryCreate) -> tuple[PMSDailyTaskEntry, str]:
        target_user_id = payload.user_id
        user = self.db.get(User, target_user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
        if payload.error_level in {'MINOR', 'MAJOR'} and not (payload.error_remark or '').strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'Error Remark is required for {user.full_name or user.email} (Minor/Major error)')

        score_items = [item.model_dump(mode='json') for item in payload.score_items]
        for item in score_items:
            max_score = int(item.get('max_score') or 0)
            value = int(item.get('value') or 0)
            if value < 0:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'Score cannot be negative for {item.get("label", "a task")}')
            if max_score and value > max_score:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'Score cannot exceed {max_score} for {item.get("label", "a task")}')

        sla_score = payload.sla_score or 0
        if sla_score < 0 or sla_score > self.SLA_MAX:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'SLA score must be between 0 and {self.SLA_MAX}')

        if payload.error_level == 'MAJOR':
            score_items = [{**item, 'value': 0} for item in score_items]
            sla_score = 0

        final_score = self.calculate_final(score_items, sla_score, payload.error_level)

        try:
            day_type = PMSDayType(payload.day_type)
            error_level = PMSErrorLevel(payload.error_level)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Invalid PMS dropdown value') from exc

        values = {
            'entry_date': payload.entry_date,
            'day_type': day_type,
            'score_items': score_items,
            'final_score_percent': final_score,
            'sla_score': sla_score,
            'error_level': error_level,
            'error_remark': payload.error_remark,
            'remarks': payload.remarks,
            'particulars_error_note': payload.particulars_error_note,
            'sla_remarks': payload.sla_remarks,
        }

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
        return entry, action

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
            user_email=entry.user.email if entry.user else None,
            entry_date=entry.entry_date,
            day_type=entry.day_type.value,
            final_score_percent=entry.final_score_percent,
            sla_score=entry.sla_score,
            score_items=[PMSScoreItem(**item) for item in (entry.score_items or [])],
            error_level=entry.error_level.value,
            error_remark=entry.error_remark,
            remarks=entry.remarks,
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
        applicable = [item for item in score_items if item.get('status') != 'NOT_APPLICABLE']
        earned = sum(min(int(item.get('value') or 0), int(item.get('max_score') or 1)) for item in applicable)
        possible = sum(int(item.get('max_score') or 1) for item in applicable)
        if sla_score is not None:
            earned += max(0, min(int(sla_score or 0), self.SLA_MAX))
            possible += self.SLA_MAX
        return round((earned / possible) * 100) if possible else 0

    def _auto_entry(self, user_id: UUID, entry_date: date):
        start = datetime.combine(entry_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        items = self._assigned_task_items(user_id, entry_date, start, end)
        return PMSDailyTaskEntry(
            user_id=user_id,
            entry_date=entry_date,
            day_type=PMSDayType.WORKING_DAY,
            score_items=items,
            final_score_percent=0,
            sla_score=0,
            error_level=PMSErrorLevel.NO_ERROR,
            remarks=None,
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
        activity_count = None
        status_value = 'NOT_ENTERED'
        if source == 'AUTO':
            # Any qualifying activity at all earns full marks by default; the admin can
            # still lower it manually. A zero-activity result is also left editable
            # (not locked as NOT_APPLICABLE) so the admin can enter marks by hand if the
            # automatic fetch is wrong, missing, or fails for some other reason.
            activity_count = self._automatic_count(subtask, user_id, start, end)
            value = max_score if activity_count > 0 else 0
            status_value = 'ENTERED' if activity_count > 0 else 'NOT_ENTERED'
        return self._item(
            f'assignment:{assignment.id}',
            label,
            value,
            max_score,
            source,
            status=status_value,
            activity_count=activity_count,
            message_type_id=subtask.source_reference_id if subtask.source_type == SubtaskSourceType.MESSAGE_TYPE else None,
            subtask_id=subtask.id,
        )

    def _automatic_count(self, subtask: Subtask, user_id: UUID, start: datetime, end: datetime) -> int:
        if subtask.source_type == SubtaskSourceType.MESSAGE_TYPE and subtask.source_reference_id:
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
        if subtask.source_type == SubtaskSourceType.OFFER_MANAGEMENT:
            return int(self.db.scalar(
                select(func.count())
                .select_from(OfferManagementEntry)
                .where(
                    OfferManagementEntry.created_by_user_id == user_id,
                    OfferManagementEntry.offer_date == start.date(),
                )
            ) or 0)
        return 0

    def _item(self, key: str, label: str, value: int, max_score: int, source: str, *, status: str | None = None, activity_count: int | None = None, message_type_id: UUID | None = None, subtask_id: UUID | None = None) -> dict:
        return {
            'key': key,
            'label': label,
            'value': value,
            'max_score': max_score,
            'status': status or ('ENTERED' if value > 0 else 'NOT_ENTERED'),
            'source': source,
            'activity_count': activity_count,
            'message_type_id': str(message_type_id) if message_type_id else None,
            'subtask_id': str(subtask_id) if subtask_id else None,
        }

    def _snapshot(self, entry: PMSDailyTaskEntry) -> dict:
        return {
            'entry_date': entry.entry_date.isoformat(),
            'score_items': entry.score_items,
            'final_score_percent': entry.final_score_percent,
            'sla_score': entry.sla_score,
            'error_level': entry.error_level.value,
            'error_remark': entry.error_remark,
            'remarks': entry.remarks,
        }

    def _entry(self, user_id: UUID, entry_date: date):
        return self.db.scalar(select(PMSDailyTaskEntry).options(joinedload(PMSDailyTaskEntry.user), joinedload(PMSDailyTaskEntry.created_by), joinedload(PMSDailyTaskEntry.updated_by)).where(PMSDailyTaskEntry.user_id == user_id, PMSDailyTaskEntry.entry_date == entry_date))

    def _require_admin(self, current_user) -> None:
        if not is_admin(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins can create or edit Daily Entry records')