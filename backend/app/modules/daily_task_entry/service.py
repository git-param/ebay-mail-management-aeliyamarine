from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.dependencies import is_admin
from app.models.conversation import Conversation, ConversationSLAHistory
from app.models.message_type import MessageClassification, MessageType
from app.models.user import User
from app.modules.offer_management.models import OfferManagementEntry
from app.modules.daily_task_entry.models import DailyTaskEntry, DailyTaskEntryErrorLevel, DailyTaskEntryHistory, DailyTaskEntryDayType, DailyTaskEntryFeedbackStatus
from app.modules.daily_task_entry.schemas import (
    DailyEntryCreate,
    DailyEntryResponse,
    DailyEntryLoadRequestUser,
    DailyEntryLoadResponseItem,
    DailyEntrySLAReviewItem,
    DailyEntrySLAReviewResponse,
    DailyEntryScoreItem,
    DailyEntryTaskLimits,
    DailyEntryUploadEntry,
    DailyEntryUploadResultItem,
)
from app.modules.sold_posting.models import SoldPostingLineItem
from app.modules.task_management.models import SubSubtask, Subtask, SubtaskSourceType, TaskCategory, TaskStatus, UserSubtaskAssignment


OTHER_GENERAL_WORK_KEY = 'other_general_work'
OTHER_GENERAL_WORK_LABEL = 'Other General Work'
OTHER_GENERAL_WORK_MAX = 10


class DailyEntryService:
    SLA_MAX = 20

    def __init__(self, db: Session):
        self.db = db

    def limits(self) -> DailyEntryTaskLimits:
        return DailyEntryTaskLimits(sla_max=self.SLA_MAX)

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
    def load(self, current_user, entry_date: date, user_id: UUID | None = None) -> list[DailyEntryLoadResponseItem]:
        self._require_admin(current_user)
        users = self._target_users(user_id)
        items: list[DailyEntryLoadResponseItem] = []
        for user in users:
            existing = self._entry(user.id, entry_date)
            entry = existing if existing else self._auto_entry(user.id, entry_date)
            items.append(DailyEntryLoadResponseItem(
                user=DailyEntryLoadRequestUser(id=user.id, full_name=user.full_name, email=user.email),
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
                User.deleted_at.is_(None),
                User.role.has(name="Support Agent"),
            )
            .order_by(User.full_name.asc())
        )

        return list(self.db.scalars(statement).all())

    def _to_base_schema(self, entry: DailyTaskEntry) -> dict:
        sla_metadata = getattr(entry, 'sla_metadata', {}) or {}
        return {
            'entry_date': entry.entry_date,
            'day_type': entry.day_type.value,
            'final_score_percent': entry.final_score_percent or 0,
            'sla_score': entry.sla_score or 0,
            'sla_met_count': sla_metadata.get('met_count'),
            'sla_total_count': sla_metadata.get('total_count'),
            'sla_auto_fetched': bool(sla_metadata.get('auto_fetched')),
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
    def save(self, current_user, payload: DailyEntryCreate) -> DailyTaskEntry:
        self._require_admin(current_user)
        entry, _ = self._save_one(current_user, payload)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    # ------------------------------------------------------------------
    # Bulk upload: create-or-update per user/date, one DB transaction,
    # per-user success/failure reporting.
    # ------------------------------------------------------------------
    def upload(self, current_user, entries: list[DailyEntryUploadEntry]) -> list[DailyEntryUploadResultItem]:
        self._require_admin(current_user)
        results: list[DailyEntryUploadResultItem] = []
        for payload in entries:
            try:
                with self.db.begin_nested():
                    entry, _ = self._save_one(current_user, payload)
                    self.db.flush()
                results.append(DailyEntryUploadResultItem(user_id=payload.user_id, success=True, entry_id=entry.id))
            except HTTPException as exc:
                results.append(DailyEntryUploadResultItem(user_id=payload.user_id, success=False, error=str(exc.detail)))
            except Exception as exc:  # noqa: BLE001 - surface to caller per-row instead of failing the whole batch
                results.append(DailyEntryUploadResultItem(user_id=payload.user_id, success=False, error=str(exc)))
        self.db.commit()
        return results

    def delete_entries(self, current_user, *, date_from: date, date_to: date, user_id: UUID | None = None) -> int:
        self._require_admin(current_user)
        if date_from > date_to:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='From date cannot be after To date')

        user_ids: list[UUID] | None = None
        if user_id:
            user_ids = [user.id for user in self._target_users(user_id)]

        entry_statement = select(DailyTaskEntry.id).where(
            DailyTaskEntry.entry_date >= date_from,
            DailyTaskEntry.entry_date <= date_to,
        )
        if user_ids is not None:
            entry_statement = entry_statement.where(DailyTaskEntry.user_id.in_(user_ids))

        entry_ids = list(self.db.scalars(entry_statement).all())
        if not entry_ids:
            return 0

        self.db.execute(delete(DailyTaskEntryHistory).where(DailyTaskEntryHistory.entry_id.in_(entry_ids)))
        result = self.db.execute(delete(DailyTaskEntry).where(DailyTaskEntry.id.in_(entry_ids)))
        self.db.commit()
        return int(result.rowcount or 0)

    def _save_one(self, current_user, payload: DailyEntryCreate) -> tuple[DailyTaskEntry, str]:
        target_user_id = payload.user_id
        user = self.db.get(User, target_user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
        if payload.error_level in {'MINOR', 'MAJOR'} and not (payload.error_remark or '').strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'Error Remark is required for {user.full_name or user.email} (Minor/Major error)')

        score_items = [item.model_dump(mode='json') for item in payload.score_items]
        for item in score_items:
            max_score = float(item.get('max_score') or 0)
            value = float(item.get('value') or 0)
            if value < 0:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'Score cannot be negative for {item.get("label", "a task")}')
            if max_score and value > max_score:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'Score cannot exceed {max_score:g} for {item.get("label", "a task")}')

        sla_score = payload.sla_score or 0
        if sla_score < 0 or sla_score > self.SLA_MAX:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'SLA score must be between 0 and {self.SLA_MAX}')

        if payload.error_level == 'MAJOR':
            score_items = [{**item, 'value': 0} for item in score_items]
            sla_score = 0

        final_score = self.calculate_final(score_items, sla_score, payload.error_level)

        try:
            day_type = DailyTaskEntryDayType(payload.day_type)
            error_level = DailyTaskEntryErrorLevel(payload.error_level)
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
            entry = DailyTaskEntry(user_id=target_user_id, created_by_user_id=current_user.id, updated_by_user_id=current_user.id, **values)
            self.db.add(entry)
            self.db.flush()
        self.db.add(DailyTaskEntryHistory(entry_id=entry.id, changed_by_user_id=current_user.id, action=action, snapshot=self._snapshot(entry)))
        return entry, action

    def list_entries(self, current_user, *, date_from: date | None = None, date_to: date | None = None, user_id: UUID | None = None):
        statement = select(DailyTaskEntry).options(joinedload(DailyTaskEntry.user), joinedload(DailyTaskEntry.created_by), joinedload(DailyTaskEntry.updated_by))
        if not is_admin(current_user):
            statement = statement.where(DailyTaskEntry.user_id == current_user.id)
        elif user_id:
            statement = statement.where(DailyTaskEntry.user_id == user_id)
        if date_from:
            statement = statement.where(DailyTaskEntry.entry_date >= date_from)
        if date_to:
            statement = statement.where(DailyTaskEntry.entry_date <= date_to)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = list(self.db.scalars(statement.order_by(DailyTaskEntry.entry_date.desc(), DailyTaskEntry.created_at.desc())))
        return items, total

    def serialize(self, entry: DailyTaskEntry) -> DailyEntryResponse:
        return DailyEntryResponse(
            id=entry.id,
            user_id=entry.user_id,
            user_name=(entry.user.full_name or entry.user.email) if entry.user else '',
            user_email=entry.user.email if entry.user else None,
            entry_date=entry.entry_date,
            day_type=entry.day_type.value,
            final_score_percent=entry.final_score_percent,
            sla_score=entry.sla_score,
            score_items=[DailyEntryScoreItem(**item) for item in (entry.score_items or [])],
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
        """Calculate PMS from normalized task performance and normalized SLA performance.

        Each applicable subtask is scored against its own configured maximum first,
        so a 20-point task does not carry twice the PMS weight of a 10-point task.
        The task percentages are averaged, SLA is converted from /20 to a percentage,
        and the two percentages contribute equally to the final PMS result.
        """
        if error_level == 'MAJOR':
            return 0

        # Only explicitly ENTERED rows participate in the daily task average.
        # Zero/no-activity rows default to NOT_APPLICABLE. An admin can explicitly
        # mark one ENTERED with value 0 when zero should count as a real 0% result.
        applicable = [item for item in score_items if item.get('status') == 'ENTERED']
        task_percentages: list[float] = []
        for item in applicable:
            max_score = max(0.01, float(item.get('max_score') or 1))
            value = max(0.0, min(float(item.get('value') or 0), max_score))
            task_percentages.append((value / max_score) * 100)

        task_average_percent = (sum(task_percentages) / len(task_percentages)) if task_percentages else 0.0
        normalized_sla = max(0, min(int(sla_score or 0), self.SLA_MAX))
        sla_percent = (normalized_sla / self.SLA_MAX) * 100

        final_percent = (task_average_percent + sla_percent) / 2
        return round(max(0.0, min(final_percent, 100.0)))

    def _auto_entry(self, user_id: UUID, entry_date: date):
        start = datetime.combine(entry_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        assignments = self._active_assignments(user_id, entry_date)
        items = [self._assignment_item(assignment, user_id, start, end) for assignment in assignments]
        other_item = self._other_general_work_item(assignments, user_id, start, end)
        if other_item is not None:
            items.append(other_item)
        sla_met_count, sla_total_count = self._sla_counts(user_id, start, end)
        sla_score = round((sla_met_count / sla_total_count) * self.SLA_MAX) if sla_total_count else self.SLA_MAX
        entry = DailyTaskEntry(
            user_id=user_id,
            entry_date=entry_date,
            day_type=DailyTaskEntryDayType.WORKING_DAY,
            score_items=items,
            final_score_percent=self.calculate_final(items, sla_score, DailyTaskEntryErrorLevel.NO_ERROR.value),
            sla_score=sla_score,
            error_level=DailyTaskEntryErrorLevel.NO_ERROR,
            remarks=None,
            particulars_error_note='NA',
            sla_remarks=f'AUTO FETCHED \u00b7 {sla_met_count}/{sla_total_count} UNDER SLA',
        )
        entry.sla_metadata = {'auto_fetched': True, 'met_count': sla_met_count, 'total_count': sla_total_count}
        return entry

    def _active_assignments(self, user_id: UUID, entry_date: date) -> list[UserSubtaskAssignment]:
        return list(self.db.scalars(
            select(UserSubtaskAssignment)
            .options(
                selectinload(UserSubtaskAssignment.subtask).selectinload(Subtask.category),
                selectinload(UserSubtaskAssignment.sub_subtask),
            )
            .join(UserSubtaskAssignment.subtask)
            .join(Subtask.category)
            .outerjoin(UserSubtaskAssignment.sub_subtask)
            .where(
                UserSubtaskAssignment.user_id == user_id,
                UserSubtaskAssignment.status == TaskStatus.ACTIVE,
                UserSubtaskAssignment.effective_from <= entry_date,
                ((UserSubtaskAssignment.effective_to.is_(None)) | (UserSubtaskAssignment.effective_to >= entry_date)),
                Subtask.status == TaskStatus.ACTIVE,
                TaskCategory.status == TaskStatus.ACTIVE,
                or_(UserSubtaskAssignment.sub_subtask_id.is_(None), SubSubtask.status == TaskStatus.ACTIVE),
            )
            .order_by(UserSubtaskAssignment.display_order, Subtask.display_order, SubSubtask.display_order, Subtask.name, SubSubtask.name)
        ))

    def _assigned_task_items(self, user_id: UUID, entry_date: date, start: datetime, end: datetime) -> list[dict]:
        # Retained for any other callers; _auto_entry now builds assignments itself
        # so it can also compute Other General Work from the same assignment set.
        assignments = self._active_assignments(user_id, entry_date)
        return [self._assignment_item(assignment, user_id, start, end) for assignment in assignments]

    def _assignment_item(self, assignment: UserSubtaskAssignment, user_id: UUID, start: datetime, end: datetime) -> dict:
        subtask = assignment.subtask
        child = assignment.sub_subtask
        target = child or subtask
        max_score = max(0.01, round(float(assignment.quality_weight or 0), 2))
        subtask_label = f'{subtask.category.name} - {subtask.name}' if subtask.category else subtask.name
        label = f'{subtask_label} - {child.name}' if child else subtask_label
        source = 'AUTO' if assignment.auto_fetch_enabled and target.supports_automatic_fetch else 'MANUAL'
        value = max_score
        activity_count = None
        status_value = 'ENTERED'
        if source == 'AUTO':
            activity_count = self._automatic_count(target, user_id, start, end)
        return self._item(
            f'assignment:{assignment.id}',
            label,
            value,
            max_score,
            source,
            status=status_value,
            activity_count=activity_count,
            message_type_id=target.source_reference_id if target.source_type == SubtaskSourceType.MESSAGE_TYPE else None,
            subtask_id=subtask.id,
            sub_subtask_id=child.id if child else None,
        )

    def _automatic_count(self, target: Subtask | SubSubtask, user_id: UUID, start: datetime, end: datetime) -> int:
        if target.source_type == SubtaskSourceType.MESSAGE_TYPE and target.source_reference_id:
            return int(self.db.scalar(
                select(func.count())
                .select_from(MessageClassification)
                .where(
                    MessageClassification.user_id == user_id,
                    MessageClassification.message_type_id == target.source_reference_id,
                    MessageClassification.created_at >= start,
                    MessageClassification.created_at < end,
                )
            ) or 0)
        if target.source_type == SubtaskSourceType.SOLD_POSTING:
            return int(self.db.scalar(
                select(func.count())
                .select_from(SoldPostingLineItem)
                .where(
                    SoldPostingLineItem.copied_by_user_id == user_id,
                    SoldPostingLineItem.copied_at >= start,
                    SoldPostingLineItem.copied_at < end,
                )
            ) or 0)
        if target.source_type == SubtaskSourceType.OFFER_MANAGEMENT:
            return int(self.db.scalar(
                select(func.count())
                .select_from(OfferManagementEntry)
                .where(
                    OfferManagementEntry.created_by_user_id == user_id,
                    OfferManagementEntry.offer_date == start.date(),
                )
            ) or 0)
        return 0

    # ------------------------------------------------------------------
    # Other General Work: activity performed by the agent that falls
    # outside their currently assigned tasks for the date.
    # ------------------------------------------------------------------
    def _other_general_work_item(self, assignments: list[UserSubtaskAssignment], user_id: UUID, start: datetime, end: datetime) -> dict | None:
        breakdown: list[dict] = []
        total_count = 0

        # MESSAGE_TYPE: any message type IDs already covered by an assignment stay
        # excluded here so activity is never counted twice. Conversation IDs are kept
        # per row so the fetched-breakdown tooltip can link straight to each
        # conversation, even when the reply never opened an SLA cycle.
        assigned_message_type_ids = {
            (assignment.sub_subtask or assignment.subtask).source_reference_id
            for assignment in assignments
            if (assignment.sub_subtask or assignment.subtask).source_type == SubtaskSourceType.MESSAGE_TYPE and (assignment.sub_subtask or assignment.subtask).source_reference_id
        }
        message_type_breakdown = self._unassigned_message_type_conversations(user_id, start, end, assigned_message_type_ids)
        for label, conversation_ids in message_type_breakdown:
            breakdown.append({'label': label, 'count': len(conversation_ids), 'conversation_ids': [str(cid) for cid in conversation_ids]})
            total_count += len(conversation_ids)

        # SOLD_POSTING / OFFER_MANAGEMENT: entire source is either assigned to this
        # agent (already scored in its own task item above) or it is not assigned at
        # all, in which case every record for the date belongs in Other General Work.
        has_sold_posting_assignment = any((a.sub_subtask or a.subtask).source_type == SubtaskSourceType.SOLD_POSTING for a in assignments)
        if not has_sold_posting_assignment:
            count = int(self.db.scalar(
                select(func.count())
                .select_from(SoldPostingLineItem)
                .where(
                    SoldPostingLineItem.copied_by_user_id == user_id,
                    SoldPostingLineItem.copied_at >= start,
                    SoldPostingLineItem.copied_at < end,
                )
            ) or 0)
            if count:
                breakdown.append({'label': 'Sold Posting', 'count': count})
                total_count += count

        has_offer_management_assignment = any((a.sub_subtask or a.subtask).source_type == SubtaskSourceType.OFFER_MANAGEMENT for a in assignments)
        if not has_offer_management_assignment:
            count = int(self.db.scalar(
                select(func.count())
                .select_from(OfferManagementEntry)
                .where(
                    OfferManagementEntry.created_by_user_id == user_id,
                    OfferManagementEntry.offer_date == start.date(),
                )
            ) or 0)
            if count:
                breakdown.append({'label': 'Offer Management', 'count': count})
                total_count += count

        item = self._item(
            OTHER_GENERAL_WORK_KEY,
            OTHER_GENERAL_WORK_LABEL,
            OTHER_GENERAL_WORK_MAX,
            OTHER_GENERAL_WORK_MAX,
            'AUTO',
            status='ENTERED',
            activity_count=total_count,
        )
        item['breakdown'] = breakdown
        return item

    def _unassigned_message_type_conversations(self, user_id: UUID, start: datetime, end: datetime, assigned_message_type_ids: set[UUID]) -> list[tuple[str, list[UUID]]]:
        # One row per classified reply, not grouped/counted in SQL, so each row's
        # conversation_id can be surfaced to the frontend for direct navigation.
        query = (
            select(MessageType.name, MessageClassification.conversation_id)
            .select_from(MessageClassification)
            .join(MessageType, MessageType.id == MessageClassification.message_type_id)
            .where(
                MessageClassification.user_id == user_id,
                MessageClassification.created_at >= start,
                MessageClassification.created_at < end,
            )
        )
        if assigned_message_type_ids:
            query = query.where(MessageClassification.message_type_id.not_in(assigned_message_type_ids))
        query = query.order_by(MessageType.name)

        grouped: dict[str, list[UUID]] = {}
        for name, conversation_id in self.db.execute(query):
            # A buyer can be replied to more than once under the same message type in
            # a day; de-duplicate so one conversation isn't listed/linked twice.
            bucket = grouped.setdefault(name, [])
            if conversation_id not in bucket:
                bucket.append(conversation_id)
        return list(grouped.items())

    def _sla_counts(self, user_id: UUID, start: datetime, end: datetime) -> tuple[int, int]:
        # Reuse completed SLA history cycles; repeated buyer messages before one
        # reply already roll into a single cycle in SLAService.
        total = int(self.db.scalar(
            select(func.count())
            .select_from(ConversationSLAHistory)
            .where(
                ConversationSLAHistory.replied_by == user_id,
                ConversationSLAHistory.replied_time >= start,
                ConversationSLAHistory.replied_time < end,
                ConversationSLAHistory.sla_met.is_not(None),
            )
        ) or 0)
        met = int(self.db.scalar(
            select(func.count())
            .select_from(ConversationSLAHistory)
            .where(
                ConversationSLAHistory.replied_by == user_id,
                ConversationSLAHistory.replied_time >= start,
                ConversationSLAHistory.replied_time < end,
                ConversationSLAHistory.sla_met.is_(True),
            )
        ) or 0)
        return met, total

    # ------------------------------------------------------------------
    # SLA Conversation Review: same filter criteria as _sla_counts so the
    # review list and the x/y UNDER SLA total can never disagree.
    # ------------------------------------------------------------------
    def sla_review(self, current_user, user_id: UUID, entry_date: date) -> DailyEntrySLAReviewResponse:
        self._require_admin(current_user)
        user = self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

        start = datetime.combine(entry_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)

        query = (
            select(ConversationSLAHistory, Conversation)
            .join(Conversation, Conversation.id == ConversationSLAHistory.conversation_id)
            .where(
                ConversationSLAHistory.replied_by == user_id,
                ConversationSLAHistory.replied_time >= start,
                ConversationSLAHistory.replied_time < end,
                ConversationSLAHistory.sla_met.is_not(None),
            )
            .order_by(ConversationSLAHistory.replied_time.asc())
        )

        rows = list(self.db.execute(query))
        seller_by_conversation = self._latest_seller_labels({conversation.id for _, conversation in rows})

        items = [
            DailyEntrySLAReviewItem(
                id=history.id,
                conversation_id=conversation.id,
                cycle_number=history.cycle_number,
                buyer=conversation.buyer_identifier,
                provider_conversation_id=conversation.provider_conversation_id,
                seller=seller_by_conversation.get(conversation.id),
                buyer_message_time=history.buyer_message_time,
                replied_time=history.replied_time,
                response_duration_seconds=history.response_duration_seconds,
                sla_met=history.sla_met,
            )
            for history, conversation in rows
        ]
        met_count = sum(1 for item in items if item.sla_met)
        return DailyEntrySLAReviewResponse(user_id=user_id, entry_date=entry_date, met_count=met_count, total_count=len(items), items=items)

    def _latest_seller_labels(self, conversation_ids: set[UUID]) -> dict[UUID, str | None]:
        # Best-effort: ConversationSLAHistory has no direct seller-account link, so
        # fall back to the most recent classified message's seller account, mirroring
        # how Message Reports resolves seller labels.
        if not conversation_ids:
            return {}
        from app.models.ebay_account import EbayAccount

        query = (
            select(MessageClassification.conversation_id, EbayAccount, MessageClassification.created_at)
            .join(EbayAccount, EbayAccount.id == MessageClassification.seller_account_id)
            .where(MessageClassification.conversation_id.in_(conversation_ids))
            .order_by(MessageClassification.conversation_id, MessageClassification.created_at.desc())
        )
        labels: dict[UUID, str | None] = {}
        for conversation_id, account, _ in self.db.execute(query):
            if conversation_id in labels:
                continue
            labels[conversation_id] = account.account_name or account.store_name or account.ebay_username
        return labels

    def _item(self, key: str, label: str, value: float, max_score: float, source: str, *, status: str | None = None, activity_count: int | None = None, message_type_id: UUID | None = None, subtask_id: UUID | None = None, sub_subtask_id: UUID | None = None) -> dict:
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
            'sub_subtask_id': str(sub_subtask_id) if sub_subtask_id else None,
        }

    def _snapshot(self, entry: DailyTaskEntry) -> dict:
        return {
            'entry_date': entry.entry_date.isoformat(),
            'score_items': entry.score_items,
            'final_score_percent': entry.final_score_percent,
            'sla_score': entry.sla_score,
            'error_level': entry.error_level.value,
            'error_remark': entry.error_remark,
        }

    def _entry(self, user_id: UUID, entry_date: date):
        return self.db.scalar(select(DailyTaskEntry).options(joinedload(DailyTaskEntry.user), joinedload(DailyTaskEntry.created_by), joinedload(DailyTaskEntry.updated_by)).where(DailyTaskEntry.user_id == user_id, DailyTaskEntry.entry_date == entry_date))

    def _require_admin(self, current_user) -> None:
        if not is_admin(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins can create or edit Daily Entry records')
