from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import is_admin
from app.models.conversation import ConversationSLAHistory
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

<<<<<<< Updated upstream
=======
    def _auto_metric_value(
        self,
        kind: str,
        user_id: UUID,
        year: int,
        month: int,
        weight: float,
    ) -> tuple[float, dict]:
        aggregates = self._compute_auto_aggregates(
            user_id,
            year,
            month,
        )

        pct = aggregates[kind]['pct']
        meta = aggregates[kind]['meta']

        value = round(
            min(
                max((pct / 100) * weight, 0.0),
                weight,
            ),
            2,
        )

        return value, meta

    def _leave_metric_value(
        self,
        metric_key: str,
        user_id: UUID,
        year: int,
        month: int,
        weight: float,
    ) -> tuple[float, dict] | None:
        if metric_key not in {'attendance', 'punctuality'}:
            return None

        from app.modules.leave_management.service import LeaveManagementService

        impact = LeaveManagementService(self.db).pms_impact_for_user_month(
            user_id,
            year,
            month,
        )

        deduction_key = (
            'attendance_deduction'
            if metric_key == 'attendance'
            else 'punctuality_deduction'
        )
        deduction = float(impact[deduction_key])

        return round(max(weight - deduction, 0.0), 2), {
            'formula': (
                'Leave Management approved excess usage only. '
                'Valid paid leave and non-approved leave do not reduce PMS.'
            ),
            'attendance_deduction': impact['attendance_deduction'],
            'punctuality_deduction': impact['punctuality_deduction'],
            'excess_paid_occurrences': impact['excess_paid_occurrences'],
            'approved_instances': impact['approved_instances'],
            'extra_instances': impact['extra_instances'],
        }

    def apply_leave_impact_to_existing_record(
        self,
        user_id: UUID,
        year: int,
        month: int,
        current_user,
    ) -> PmsMonthlyRecord | None:
        record = self._get_record(user_id, year, month)

        if not record:
            return None

        changed = False

        for metric in record.metrics:
            leave_value = self._leave_metric_value(
                metric.metric_key,
                user_id,
                year,
                month,
                float(metric.weight_snapshot),
            )

            if not leave_value:
                continue

            value, meta = leave_value

            if (
                round(float(metric.final_value), 2) != value
                or metric.calc_meta != meta
                or not metric.is_auto_calculated_snapshot
            ):
                metric.source_snapshot = PmsMetricSource.CUSTOM.value
                metric.is_auto_calculated_snapshot = True
                metric.auto_value = value
                metric.final_value = value
                metric.was_overridden = False
                metric.calc_meta = meta
                changed = True

        if not changed:
            return None

        record.final_score = round(
            sum(float(metric.final_value) for metric in record.metrics),
            2,
        )
        record.updated_by_user_id = current_user.id
        self._recalculate_employee_of_month(year, month)
        self.db.flush()

        return record

>>>>>>> Stashed changes
    # ------------------------------------------------------------------
    # Single-entry save (kept for backward compatibility)
    # ------------------------------------------------------------------
<<<<<<< Updated upstream
    def save(self, current_user, payload: PMSDailyEntryCreate) -> PMSDailyTaskEntry:
        self._require_admin(current_user)
        entry, _ = self._save_one(current_user, payload)
=======
    def _get_record(
        self,
        user_id: UUID,
        year: int,
        month: int,
    ) -> PmsMonthlyRecord | None:
        # IMPORTANT:
        # `metrics` is a one-to-many collection. selectinload avoids duplicate
        # parent rows and the SQLAlchemy unique() requirement caused by
        # joinedload on collection relationships.
        return self.db.scalar(
            select(PmsMonthlyRecord)
            .options(
                selectinload(PmsMonthlyRecord.metrics),
                joinedload(PmsMonthlyRecord.user),
                joinedload(PmsMonthlyRecord.updated_by),
            )
            .where(
                PmsMonthlyRecord.user_id == user_id,
                PmsMonthlyRecord.year == year,
                PmsMonthlyRecord.month == month,
            )
        )

    def get_monthly_record(
        self,
        current_user,
        user_id: UUID,
        year: int,
        month: int,
    ) -> PmsMonthlyRecordResponse:
        self._authorize_self_or_privileged(
            current_user,
            user_id,
        )

        user = self.db.get(User, user_id)

        if not user:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                'User not found',
            )

        record = self._get_record(
            user_id,
            year,
            month,
        )

        if record:
            return self._serialize_record(
                record,
                user,
            )

        # Nothing saved yet: build a live unsaved draft using the active
        # configuration plus fresh auto calculations.
        configs, _ = self.list_config(
            include_inactive=False
        )

        metrics: list[PmsMonthlyMetricSchema] = []

        for config in configs:
            leave_value = self._leave_metric_value(
                config.key,
                user_id,
                year,
                month,
                float(config.weight),
            )

            if leave_value:
                value, meta = leave_value

                metrics.append(
                    PmsMonthlyMetricSchema(
                        metric_key=config.key,
                        metric_name_snapshot=config.name,
                        weight_snapshot=float(config.weight),
                        source_snapshot=PmsMetricSource.CUSTOM.value,
                        is_auto_calculated_snapshot=True,
                        auto_value=value,
                        final_value=value,
                        was_overridden=False,
                        calc_meta=meta,
                    )
                )

            elif config.source in (
                PmsMetricSource.PRODUCTIVITY_AUTO,
                PmsMetricSource.QUALITY_AUTO,
            ):
                kind = (
                    'productivity'
                    if config.source
                    == PmsMetricSource.PRODUCTIVITY_AUTO
                    else 'quality'
                )

                value, meta = self._auto_metric_value(
                    kind,
                    user_id,
                    year,
                    month,
                    float(config.weight),
                )

                metrics.append(
                    PmsMonthlyMetricSchema(
                        metric_key=config.key,
                        metric_name_snapshot=config.name,
                        weight_snapshot=float(config.weight),
                        source_snapshot=config.source.value,
                        is_auto_calculated_snapshot=True,
                        auto_value=value,
                        final_value=value,
                        was_overridden=False,
                        calc_meta=meta,
                    )
                )
            else:
                metrics.append(
                    PmsMonthlyMetricSchema(
                        metric_key=config.key,
                        metric_name_snapshot=config.name,
                        weight_snapshot=float(config.weight),
                        source_snapshot=config.source.value,
                        is_auto_calculated_snapshot=False,
                        auto_value=None,
                        final_value=0,
                        was_overridden=False,
                        calc_meta=None,
                    )
                )

        return PmsMonthlyRecordResponse(
            id=None,
            user_id=user.id,
            user_name=user.full_name or user.email,
            user_email=user.email,
            year=year,
            month=month,
            status='DRAFT',
            final_score=round(
                sum(m.final_value for m in metrics),
                2,
            ),
            maximum_score=round(
                sum(m.weight_snapshot for m in metrics),
                2,
            ),
            remarks=None,
            metrics=metrics,
        )

    def refresh_auto_values(
        self,
        current_user,
        payload: PmsMonthlyRefreshRequest,
    ) -> PmsMonthlyRecordResponse:
        self._require_admin(current_user)

        record = self._get_record(
            payload.user_id,
            payload.year,
            payload.month,
        )

        if not record:
            # Nothing saved yet — refresh simply regenerates the live draft.
            return self.get_monthly_record(
                current_user,
                payload.user_id,
                payload.year,
                payload.month,
            )

        for metric in record.metrics:
            leave_value = self._leave_metric_value(
                metric.metric_key,
                payload.user_id,
                payload.year,
                payload.month,
                float(metric.weight_snapshot),
            )

            if leave_value:
                value, meta = leave_value
                metric.source_snapshot = PmsMetricSource.CUSTOM.value
                metric.is_auto_calculated_snapshot = True
                metric.auto_value = value
                metric.final_value = value
                metric.was_overridden = False
                metric.calc_meta = meta
                continue

            if (
                metric.source_snapshot
                == PmsMetricSource.PRODUCTIVITY_AUTO.value
            ):
                kind = 'productivity'

            elif (
                metric.source_snapshot
                == PmsMetricSource.QUALITY_AUTO.value
            ):
                kind = 'quality'

            else:
                continue

            value, meta = self._auto_metric_value(
                kind,
                payload.user_id,
                payload.year,
                payload.month,
                float(metric.weight_snapshot),
            )

            metric.auto_value = value
            metric.calc_meta = meta

            # Refreshing automatic values must never silently overwrite an
            # Admin's deliberate manual override.
            if not metric.was_overridden:
                metric.final_value = value

        record.final_score = round(
            sum(
                float(metric.final_value)
                for metric in record.metrics
            ),
            2,
        )

        record.updated_by_user_id = current_user.id

        self.db.flush()

        self.audit.log(
            action='PMS_AUTO_VALUES_REFRESHED',
            user_id=current_user.id,
            entity_type='PMS_MONTHLY_RECORD',
            entity_id=record.id,
            category='PMS_MANAGEMENT',
            metadata={
                'employee_user_id': str(payload.user_id),
                'year': payload.year,
                'month': payload.month,
            },
        )

>>>>>>> Stashed changes
        self.db.commit()
        self.db.refresh(entry)
        return entry

    # ------------------------------------------------------------------
    # Bulk upload: create-or-update per user/date, one DB transaction,
    # per-user success/failure reporting.
    # ------------------------------------------------------------------
    def upload(self, current_user, entries: list[PMSUploadEntry]) -> list[PMSUploadResultItem]:
        self._require_admin(current_user)
<<<<<<< Updated upstream
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
=======

        user = self.db.get(
            User,
            payload.user_id,
        )

        if not user:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                'User not found',
            )

        configs, total_active_weight = self.list_config(
            include_inactive=False
        )

        input_by_key = {
            item.metric_key: item
            for item in payload.metrics
        }

        record = self._get_record(
            payload.user_id,
            payload.year,
            payload.month,
        )

        action = (
            'PMS_UPDATED'
            if record
            else 'PMS_CREATED'
        )

        if not record:
            record = PmsMonthlyRecord(
                user_id=payload.user_id,
                year=payload.year,
                month=payload.month,
                created_by_user_id=current_user.id,
            )

            self.db.add(record)
            self.db.flush()

        existing_by_key = {
            metric.metric_key: metric
            for metric in record.metrics
        }

        overridden_keys: list[str] = []
        final_score = 0.0

        for config in configs:
            weight = float(config.weight)

            entered = input_by_key.get(config.key)

            entered_value = (
                entered.final_value
                if entered is not None
                else None
            )

            if (
                entered_value is not None
                and (
                    entered_value < 0
                    or entered_value > weight
                )
            ):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f'{config.name} score cannot exceed {weight}',
                )

            leave_value = self._leave_metric_value(
                config.key,
                payload.user_id,
                payload.year,
                payload.month,
                weight,
            )

            if leave_value:
                auto_value, meta = leave_value
                final_value = auto_value
                was_overridden = False
                source_snapshot = PmsMetricSource.CUSTOM.value
                is_auto_calculated = True

            elif config.source in (
                PmsMetricSource.PRODUCTIVITY_AUTO,
                PmsMetricSource.QUALITY_AUTO,
            ):
                kind = (
                    'productivity'
                    if config.source
                    == PmsMetricSource.PRODUCTIVITY_AUTO
                    else 'quality'
                )

                auto_value, meta = self._auto_metric_value(
                    kind,
                    payload.user_id,
                    payload.year,
                    payload.month,
                    weight,
                )

                final_value = (
                    entered_value
                    if entered_value is not None
                    else auto_value
                )

                was_overridden = (
                    entered_value is not None
                    and round(float(entered_value), 2)
                    != round(float(auto_value), 2)
                )
                source_snapshot = config.source.value
                is_auto_calculated = config.is_auto_calculated
            else:
                auto_value = None
                meta = None

                final_value = (
                    entered_value
                    if entered_value is not None
                    else 0.0
                )

                was_overridden = False
                source_snapshot = config.source.value
                is_auto_calculated = config.is_auto_calculated

            final_value = round(
                max(
                    0.0,
                    min(
                        float(final_value),
                        weight,
                    ),
                ),
                2,
            )

            final_score += final_value

            if was_overridden:
                overridden_keys.append(
                    config.key
                )

            existing_metric = existing_by_key.get(
                config.key
            )

            if existing_metric:
                existing_metric.metric_name_snapshot = config.name
                existing_metric.weight_snapshot = weight
                existing_metric.source_snapshot = source_snapshot
                existing_metric.is_auto_calculated_snapshot = (
                    is_auto_calculated
                )
                existing_metric.auto_value = auto_value
                existing_metric.final_value = final_value
                existing_metric.was_overridden = was_overridden
                existing_metric.calc_meta = meta

            else:
                self.db.add(
                    PmsMonthlyMetric(
                        pms_monthly_record_id=record.id,
                        metric_key=config.key,
                        metric_name_snapshot=config.name,
                        weight_snapshot=weight,
                        source_snapshot=source_snapshot,
                        is_auto_calculated_snapshot=(
                            is_auto_calculated
                        ),
                        auto_value=auto_value,
                        final_value=final_value,
                        was_overridden=was_overridden,
                        calc_meta=meta,
                    )
                )

        record.remarks = payload.remarks
        record.status = PmsMonthlyStatus(
            payload.status
        )
        record.final_score = round(
            final_score,
            2,
        )
        record.maximum_score = total_active_weight
        record.updated_by_user_id = current_user.id

        self.db.flush()

        self.audit.log(
            action=action,
            user_id=current_user.id,
            entity_type='PMS_MONTHLY_RECORD',
            entity_id=record.id,
            category='PMS_MANAGEMENT',
            metadata={
                'employee_user_id': str(payload.user_id),
                'year': payload.year,
                'month': payload.month,
                'final_score': record.final_score,
                'status': record.status.value,
                'overridden_metrics': overridden_keys,
            },
        )

        # Re-evaluate Employee of the Month immediately after every PMS save,
        # so edits and status changes are reflected without a separate job.
        self._recalculate_employee_of_month(
            payload.year,
            payload.month,
        )

>>>>>>> Stashed changes
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
        sla_met_count, sla_total_count = self._sla_counts(user_id, start, end)
        sla_score = round((sla_met_count / sla_total_count) * self.SLA_MAX) if sla_total_count else 0
        entry = PMSDailyTaskEntry(
            user_id=user_id,
            entry_date=entry_date,
            day_type=PMSDayType.WORKING_DAY,
            score_items=items,
            final_score_percent=self.calculate_final(items, sla_score, PMSErrorLevel.NO_ERROR.value),
            sla_score=sla_score,
            error_level=PMSErrorLevel.NO_ERROR,
            remarks=None,
            particulars_error_note='NA',
            sla_remarks=f'AUTO FETCHED \u00b7 {sla_met_count}/{sla_total_count} UNDER SLA',
        )
        entry.sla_metadata = {'auto_fetched': True, 'met_count': sla_met_count, 'total_count': sla_total_count}
        return entry

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
