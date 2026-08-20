import calendar
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.dependencies import can_manage_operations, is_admin, is_support_agent
from app.models.user import User
from app.modules.daily_task_entry.models import (
    DailyTaskEntry,
    DailyTaskEntryDayType,
    DailyTaskEntryErrorLevel,
)
from app.modules.pms.model import (
    PmsEmployeeOfMonthSelection,
    PmsMetricConfig,
    PmsMetricSource,
    PmsMonthlyMetric,
    PmsMonthlyRecord,
    PmsMonthlyStatus,
)
from app.modules.pms.schema import (
    PmsEmployeeOfMonthCandidate,
    PmsEmployeeOfMonthResolveRequest,
    PmsEmployeeOfMonthResponse,
    PmsHistoryItem,
    PmsHistoryResponse,
    PmsMetricConfigCreate,
    PmsMetricConfigUpdate,
    PmsMonthlyMetricSchema,
    PmsMonthlyRecordResponse,
    PmsMonthlyRefreshRequest,
    PmsMonthlySaveRequest,
    PmsMonthlyTableResponse,
    PmsMonthlyTableRow,
)

# NOTE: assumed path for the existing shared audit service based on the model
# import shape (`app.models.audit_log.AuditLog`). Update this import if the
# real module lives elsewhere (e.g. app/modules/audit_logs/service.py).
from app.services.audit_service import AuditService


# Business defaults from the PMS spec (Section 5). These only seed the table
# the first time it's empty — after that, everything is Admin-configurable
# and this list is never consulted again.
DEFAULT_METRICS = [
    {
        'key': 'target_achievement',
        'name': 'Target Achievement',
        'weight': 65,
        'source': PmsMetricSource.MANUAL,
        'is_auto_calculated': False,
        'display_order': 1,
    },
    {
        'key': 'productivity',
        'name': 'Productivity',
        'weight': 10,
        'source': PmsMetricSource.PRODUCTIVITY_AUTO,
        'is_auto_calculated': True,
        'display_order': 2,
    },
    {
        'key': 'quality',
        'name': 'Quality',
        'weight': 10,
        'source': PmsMetricSource.QUALITY_AUTO,
        'is_auto_calculated': True,
        'display_order': 3,
    },
    {
        'key': 'attendance',
        'name': 'Attendance',
        'weight': 5,
        'source': PmsMetricSource.MANUAL,
        'is_auto_calculated': False,
        'display_order': 4,
    },
    {
        'key': 'punctuality',
        'name': 'Late Login / Punctuality',
        'weight': 5,
        'source': PmsMetricSource.MANUAL,
        'is_auto_calculated': False,
        'display_order': 5,
    },
    {
        'key': 'competency',
        'name': 'Competency',
        'weight': 5,
        'source': PmsMetricSource.MANUAL,
        'is_auto_calculated': False,
        'display_order': 6,
    },
]

# Support Agent role name matches the exact string already used by
# DailyEntryService._target_users, so PMS's "eligible employees" query
# stays consistent with Daily Task Entry's.
ELIGIBLE_ROLE_NAME = 'Support Agent'
MAX_DEFAULT_MANUAL_METRIC_KEYS = {'competency'}


class PmsService:
    SLA_MAX = 20  # mirrors DailyEntryService.SLA_MAX

    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    # ------------------------------------------------------------------
    # PMS Configuration
    # ------------------------------------------------------------------
    def _ensure_default_config(self) -> None:
        has_any = self.db.scalar(
            select(func.count()).select_from(PmsMetricConfig)
        )
        if has_any:
            return

        for item in DEFAULT_METRICS:
            self.db.add(
                PmsMetricConfig(
                    key=item['key'],
                    name=item['name'],
                    weight=item['weight'],
                    source=item['source'],
                    is_auto_calculated=item['is_auto_calculated'],
                    is_manually_editable=True,
                    is_active=True,
                    display_order=item['display_order'],
                )
            )

        self.db.commit()

    def list_config(
        self,
        *,
        include_inactive: bool = True,
    ) -> tuple[list[PmsMetricConfig], float]:
        self._ensure_default_config()

        statement = select(PmsMetricConfig).order_by(
            PmsMetricConfig.display_order,
            PmsMetricConfig.name,
        )

        if not include_inactive:
            statement = statement.where(PmsMetricConfig.is_active.is_(True))

        items = list(self.db.scalars(statement))

        total_active_weight = round(
            sum(float(item.weight) for item in items if item.is_active),
            2,
        )

        return items, total_active_weight

    def create_config(
        self,
        current_user,
        payload: PmsMetricConfigCreate,
    ) -> PmsMetricConfig:
        existing = self.db.scalar(
            select(PmsMetricConfig).where(
                PmsMetricConfig.key == payload.key
            )
        )

        if existing:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"A metric with key '{payload.key}' already exists",
            )

        try:
            source = PmsMetricSource(payload.source)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                'Invalid metric source',
            ) from exc

        config = PmsMetricConfig(
            key=payload.key,
            name=payload.name,
            weight=payload.weight,
            source=source,
            is_auto_calculated=payload.is_auto_calculated,
            is_manually_editable=payload.is_manually_editable,
            is_active=payload.is_active,
            display_order=payload.display_order,
            description=payload.description,
            created_by_user_id=current_user.id,
            updated_by_user_id=current_user.id,
        )

        self.db.add(config)
        self.db.flush()

        self.audit.log(
            action='PMS_CONFIG_CREATED',
            user_id=current_user.id,
            entity_type='PMS_METRIC_CONFIG',
            entity_id=config.id,
            category='PMS_MANAGEMENT',
            metadata={
                'key': config.key,
                'weight': float(config.weight),
                'source': config.source.value,
            },
        )

        self.db.commit()
        self.db.refresh(config)

        return config

    def update_config(
        self,
        current_user,
        config_id: UUID,
        payload: PmsMetricConfigUpdate,
    ) -> PmsMetricConfig:
        config = self.db.get(PmsMetricConfig, config_id)

        if not config:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                'Metric configuration not found',
            )

        old_snapshot = {
            'name': config.name,
            'weight': float(config.weight),
            'is_manually_editable': config.is_manually_editable,
            'is_active': config.is_active,
            'display_order': config.display_order,
            'description': config.description,
        }

        data = payload.model_dump(exclude_unset=True)

        if (
            'weight' in data
            and data['weight'] is not None
            and data['weight'] < 0
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                'Weight cannot be negative',
            )

        for key, value in data.items():
            setattr(config, key, value)

        config.updated_by_user_id = current_user.id

        self.db.flush()

        new_snapshot = {
            'name': config.name,
            'weight': float(config.weight),
            'is_manually_editable': config.is_manually_editable,
            'is_active': config.is_active,
            'display_order': config.display_order,
            'description': config.description,
        }

        self.audit.log(
            action='PMS_CONFIG_UPDATED',
            user_id=current_user.id,
            entity_type='PMS_METRIC_CONFIG',
            entity_id=config.id,
            category='PMS_MANAGEMENT',
            metadata={
                'old': old_snapshot,
                'new': new_snapshot,
            },
        )

        self.db.commit()
        self.db.refresh(config)

        return config

    def delete_config(
        self,
        current_user,
        config_id: UUID,
    ) -> None:
        config = self.db.get(PmsMetricConfig, config_id)

        if not config:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                'Metric configuration not found',
            )

        snapshot = {
            'key': config.key,
            'name': config.name,
            'weight': float(config.weight),
            'source': config.source.value,
            'is_active': config.is_active,
        }

        self.audit.log(
            action='PMS_CONFIG_DELETED',
            user_id=current_user.id,
            entity_type='PMS_METRIC_CONFIG',
            entity_id=config.id,
            category='PMS_MANAGEMENT',
            metadata=snapshot,
        )

        self.db.delete(config)
        self.db.commit()

    # ------------------------------------------------------------------
    # Eligible employees (mirrors DailyEntryService._target_users)
    # ------------------------------------------------------------------
    def _eligible_users(self) -> list[User]:
        statement = (
            select(User)
            .where(
                User.is_active.is_(True),
                User.role.has(name=ELIGIBLE_ROLE_NAME),
            )
            .order_by(User.full_name.asc())
        )

        return list(self.db.scalars(statement))

    # ------------------------------------------------------------------
    # Monthly Quality / Productivity aggregation from Daily Task Entry
    #
    # Rules:
    #  - Only WORKING_DAY entries count; HOLIDAY/SUNDAY/LEAVE are excluded.
    #  - A calendar date with NO DailyTaskEntry row at all is treated as an
    #    unfilled working day and scores 0% for that day.
    #  - A MAJOR error day scores 0% for both Productivity and Quality.
    #  - A MINOR error day does not zero the score, but is surfaced in meta.
    #  - Productivity = task score_items portion only, excluding SLA.
    #  - Quality = SLA portion only.
    # ------------------------------------------------------------------
    def _compute_auto_aggregates(
        self,
        user_id: UUID,
        year: int,
        month: int,
    ) -> dict:
        days_in_month = calendar.monthrange(year, month)[1]

        start = date(year, month, 1)
        end = date(year, month, days_in_month)

        entries = list(
            self.db.scalars(
                select(DailyTaskEntry).where(
                    DailyTaskEntry.user_id == user_id,
                    DailyTaskEntry.entry_date >= start,
                    DailyTaskEntry.entry_date <= end,
                )
            )
        )

        entries_by_date = {
            entry.entry_date: entry
            for entry in entries
        }
        productivity_values: list[float] = []
        quality_values: list[float] = []

        working_days = 0
        minor_error_days = 0
        major_error_days = 0

        current = start

        while current <= end:
            entry = entries_by_date.get(current)

            if entry is None:
                working_days += 1
                productivity_values.append(0.0)
                quality_values.append(0.0)

                current += timedelta(days=1)
                continue

            if entry.day_type != DailyTaskEntryDayType.WORKING_DAY:
                current += timedelta(days=1)
                continue

            working_days += 1

            if entry.error_level == DailyTaskEntryErrorLevel.MAJOR:
                major_error_days += 1
                productivity_values.append(0.0)
                quality_values.append(0.0)

                current += timedelta(days=1)
                continue

            if entry.error_level == DailyTaskEntryErrorLevel.MINOR:
                minor_error_days += 1

            items = entry.score_items or []

            applicable = [
                item
                for item in items
                if item.get('status') != 'NOT_APPLICABLE'
            ]

            possible = sum(
                int(item.get('max_score') or 1)
                for item in applicable
            )

            earned = sum(
                min(
                    int(item.get('value') or 0),
                    int(item.get('max_score') or 1),
                )
                for item in applicable
            )

            productivity_pct = (
                earned / possible * 100
                if possible
                else 0.0
            )

            quality_pct = (
                min(
                    int(entry.sla_score or 0),
                    self.SLA_MAX,
                )
                / self.SLA_MAX
                * 100
                if self.SLA_MAX
                else 0.0
            )

            productivity_values.append(productivity_pct)
            quality_values.append(quality_pct)

            current += timedelta(days=1)

        avg_productivity_pct = (
            round(
                sum(productivity_values) / len(productivity_values),
                2,
            )
            if productivity_values
            else 0.0
        )

        avg_quality_pct = (
            round(
                sum(quality_values) / len(quality_values),
                2,
            )
            if quality_values
            else 0.0
        )

        return {
            'productivity': {
                'pct': avg_productivity_pct,
                'meta': {
                    'formula': (
                        "Average of each working day's task completion % "
                        '(score_items only, SLA excluded).'
                    ),
                    'working_days': working_days,
                    'task_completion_avg_pct': avg_productivity_pct,
                    'major_error_days': major_error_days,
                },
            },
            'quality': {
                'pct': avg_quality_pct,
                'meta': {
                    'formula': (
                        "Average of each working day's SLA score "
                        '(sla_score / 20), zeroed on Major error days.'
                    ),
                    'working_days': working_days,
                    'sla_avg_pct': avg_quality_pct,
                    'minor_error_days': minor_error_days,
                    'major_error_days': major_error_days,
                },
            },
        }
    
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
                'Leave Management approved excess usage only. Paid leave is '
                'allowed up to the configured 1.5-day monthly allowance; excess '
                'paid leave days are rounded up to whole attendance deductions '
                '(for example, 3 days - 1.5 allowance = 1.5 excess = 2 points). '
                'Short leave uses the Admin-configured monthly limit and pending '
                'or approved requests consume that limit. Instance leave uses '
                'its Admin-configured limit for punctuality deductions. '
                'Non-approved leave does not reduce PMS.'
            ),
            'attendance_deduction': impact['attendance_deduction'],
            'punctuality_deduction': impact['punctuality_deduction'],
            'excess_paid_occurrences': impact['excess_paid_occurrences'],
            'approved_instances': impact['approved_instances'],
            'extra_instances': impact['extra_instances'],
            'approved_short': impact.get('approved_short', 0),
            'extra_short': impact.get('extra_short', 0),
        }

    def _manual_metric_default_value(self, metric_key: str, weight: float) -> float:
        # Competency starts at the Admin-configured maximum score for the month.
        # Admins can still edit it manually; this only controls the untouched
        # draft/default. Attendance and Late Login/Punctuality are computed by
        # `_leave_metric_value`, which starts from the configured max and applies
        # leave deductions.
        if metric_key in MAX_DEFAULT_MANUAL_METRIC_KEYS:
            return weight
        return 0.0

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

    # ------------------------------------------------------------------
    # Single-entry save (kept for backward compatibility)
    # ------------------------------------------------------------------
    def save(self, current_user, payload: PMSDailyEntryCreate) -> PMSDailyTaskEntry:
        self._require_admin(current_user)
        entry, _ = self._save_one(current_user, payload)
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

        self.db.commit()
        self.db.refresh(entry)
        return entry

    # ------------------------------------------------------------------
    # Monthly record — live draft (unsaved) or persisted
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

        self.db.commit()
        return results

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
                        final_value=self._manual_metric_default_value(config.key, float(config.weight)),
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

            if (metric.source_snapshot== PmsMetricSource.PRODUCTIVITY_AUTO.value):
                kind = 'productivity'

            elif (metric.source_snapshot== PmsMetricSource.QUALITY_AUTO.value):
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

        self.db.commit()
        self.db.refresh(record)

        user = self.db.get(
            User,
            payload.user_id,
        )

        return self._serialize_record(
            record,
            user,
        )

    # ------------------------------------------------------------------
    # Save / upsert (atomic — single DB transaction)
    # ------------------------------------------------------------------
    def save_monthly(
        self,
        current_user,
        payload: PmsMonthlySaveRequest,
    ) -> PmsMonthlyRecordResponse:
        self._require_admin(current_user)

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
                source_snapshot = config.source.value
                is_auto_calculated = config.is_auto_calculated

                final_value = (
                    entered_value
                    if entered_value is not None
                    else self._manual_metric_default_value(config.key, weight)
                )

                was_overridden = False

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

        self.db.commit()
        self.db.refresh(record)

        return self._serialize_record(
            record,
            user,
        )

    def _serialize_record(
        self,
        record: PmsMonthlyRecord,
        user: User | None,
    ) -> PmsMonthlyRecordResponse:
        return PmsMonthlyRecordResponse(
            id=record.id,
            user_id=record.user_id,
            user_name=(
                user.full_name or user.email
                if user
                else ''
            ),
            user_email=(
                user.email
                if user
                else None
            ),
            year=record.year,
            month=record.month,
            status=record.status.value,
            final_score=float(record.final_score),
            maximum_score=float(record.maximum_score),
            remarks=record.remarks,
            metrics=[
                PmsMonthlyMetricSchema(
                    metric_key=metric.metric_key,
                    metric_name_snapshot=(
                        metric.metric_name_snapshot
                    ),
                    weight_snapshot=float(
                        metric.weight_snapshot
                    ),
                    source_snapshot=(
                        metric.source_snapshot
                    ),
                    is_auto_calculated_snapshot=(
                        metric.is_auto_calculated_snapshot
                    ),
                    auto_value=(
                        float(metric.auto_value)
                        if metric.auto_value is not None
                        else None
                    ),
                    final_value=float(
                        metric.final_value
                    ),
                    was_overridden=(
                        metric.was_overridden
                    ),
                    calc_meta=metric.calc_meta,
                )
                for metric in record.metrics
            ],
            created_at=record.created_at,
            updated_at=record.updated_at,
            updated_by_name=(
                record.updated_by.full_name
                or record.updated_by.email
                if record.updated_by
                else None
            ),
        )

    # ------------------------------------------------------------------
    # Monthly overview table (Admin / Ops Manager)
    # ------------------------------------------------------------------
    def get_monthly_table(
        self,
        current_user,
        year: int,
        month: int,
        search: str | None = None,
    ) -> PmsMonthlyTableResponse:
        self._require_view_all(
            current_user
        )

        _, total_active_weight = self.list_config(
            include_inactive=False
        )

        users = self._eligible_users()

        if search:
            needle = search.lower()

            users = [
                user
                for user in users
                if (
                    needle in (
                        user.full_name or ''
                    ).lower()
                    or needle in (
                        user.email or ''
                    ).lower()
                )
            ]

        records_by_user: dict[
            UUID,
            PmsMonthlyRecord,
        ] = {}

        if users:
            found = self.db.scalars(
                select(PmsMonthlyRecord).where(
                    PmsMonthlyRecord.year == year,
                    PmsMonthlyRecord.month == month,
                    PmsMonthlyRecord.user_id.in_(
                        [user.id for user in users]
                    ),
                )
            )

            records_by_user = {
                record.user_id: record
                for record in found
            }

        items: list[PmsMonthlyTableRow] = []
        completed_scores: list[
            tuple[str, float]
        ] = []

        for user in users:
            record = records_by_user.get(
                user.id
            )

            items.append(
                PmsMonthlyTableRow(
                    user_id=user.id,
                    user_name=(
                        user.full_name
                        or user.email
                    ),
                    user_email=user.email,
                    record_id=(
                        record.id
                        if record
                        else None
                    ),
                    status=(
                        record.status.value
                        if record
                        else None
                    ),
                    final_score=(
                        float(record.final_score)
                        if record
                        else None
                    ),
                    maximum_score=(
                        float(record.maximum_score)
                        if record
                        else None
                    ),
                )
            )

            if (
                record
                and record.status
                == PmsMonthlyStatus.COMPLETED
            ):
                completed_scores.append(
                    (
                        user.full_name
                        or user.email,
                        float(record.final_score),
                    )
                )

        completed_count = len(
            completed_scores
        )

        pending_count = (
            len(users)
            - completed_count
        )

        average_score = (
            round(
                sum(
                    score
                    for _, score in completed_scores
                )
                / completed_count,
                2,
            )
            if completed_count
            else None
        )

        top = (
            max(
                completed_scores,
                key=lambda pair: pair[1],
            )
            if completed_scores
            else None
        )

        return PmsMonthlyTableResponse(
            year=year,
            month=month,
            total_active_weight=(
                total_active_weight
            ),
            items=items,
            completed_count=completed_count,
            pending_count=pending_count,
            average_score=average_score,
            top_performer_name=(
                top[0]
                if top
                else None
            ),
            top_performer_score=(
                top[1]
                if top
                else None
            ),
        )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def get_history(
        self,
        current_user,
        *,
        year: int | None = None,
        month: int | None = None,
        user_id: UUID | None = None,
        search: str | None = None,
        status_filter: str | None = None,
    ) -> PmsHistoryResponse:
        statement = (
            select(PmsMonthlyRecord)
            .options(
                joinedload(
                    PmsMonthlyRecord.user
                )
            )
        )

        if is_support_agent(
            current_user
        ):
            # An Agent is always restricted to their own records. Never trust
            # the user_id query parameter as an authorization boundary.
            statement = statement.where(
                PmsMonthlyRecord.user_id
                == current_user.id
            )

        elif user_id:
            statement = statement.where(
                PmsMonthlyRecord.user_id
                == user_id
            )

        if year:
            statement = statement.where(
                PmsMonthlyRecord.year
                == year
            )

        if month:
            statement = statement.where(
                PmsMonthlyRecord.month
                == month
            )

        if status_filter:
            statement = statement.where(
                PmsMonthlyRecord.status
                == PmsMonthlyStatus(
                    status_filter
                )
            )

        records = list(
            self.db.scalars(
                statement.order_by(
                    PmsMonthlyRecord.year.desc(),
                    PmsMonthlyRecord.month.desc(),
                )
            )
        )

        if search:
            needle = search.lower()

            records = [
                record
                for record in records
                if needle
                in (
                    (
                        record.user.full_name
                        or record.user.email
                        or ''
                    )
                    if record.user
                    else ''
                ).lower()
            ]

        items = [
            PmsHistoryItem(
                record_id=record.id,
                user_id=record.user_id,
                user_name=(
                    (
                        record.user.full_name
                        or record.user.email
                    )
                    if record.user
                    else ''
                ),
                year=record.year,
                month=record.month,
                status=record.status.value,
                final_score=float(
                    record.final_score
                ),
                maximum_score=float(
                    record.maximum_score
                ),
                percentage=(
                    round(
                        (
                            float(record.final_score)
                            / float(record.maximum_score)
                        )
                        * 100,
                        2,
                    )
                    if record.maximum_score
                    else 0.0
                ),
                updated_at=record.updated_at,
            )
            for record in records
        ]

        return PmsHistoryResponse(
            items=items,
            total=len(items),
        )

    # ------------------------------------------------------------------
    # Employee of the Month
    # ------------------------------------------------------------------
    def _recalculate_employee_of_month(
        self,
        year: int,
        month: int,
    ) -> None:
        completed = list(
            self.db.scalars(
                select(PmsMonthlyRecord).where(
                    PmsMonthlyRecord.year == year,
                    PmsMonthlyRecord.month == month,
                    PmsMonthlyRecord.status
                    == PmsMonthlyStatus.COMPLETED,
                )
            )
        )

        selection = self.db.scalar(
            select(
                PmsEmployeeOfMonthSelection
            ).where(
                PmsEmployeeOfMonthSelection.year
                == year,
                PmsEmployeeOfMonthSelection.month
                == month,
            )
        )

        if not completed:
            if selection:
                selection.is_tie = False
                selection.tied_user_ids = None
                selection.selected_user_id = None
                selection.selected_by_user_id = None
                selection.selected_at = None

            return

        top_score = max(
            float(record.final_score)
            for record in completed
        )

        top_records = [
            record
            for record in completed
            if float(record.final_score)
            == top_score
        ]

        if not selection:
            selection = (
                PmsEmployeeOfMonthSelection(
                    year=year,
                    month=month,
                )
            )

            self.db.add(selection)

        if len(top_records) == 1:
            selection.is_tie = False
            selection.tied_user_ids = None
            selection.selected_user_id = (
                top_records[0].user_id
            )
            selection.selected_by_user_id = None
            selection.selected_at = None
            selection.reason = None

        else:
            tied_ids = [
                str(record.user_id)
                for record in top_records
            ]

            # Keep a prior manual tie resolution only while that employee
            # remains one of the current top scorers.
            if not (
                selection.is_tie
                and selection.selected_user_id
                and str(
                    selection.selected_user_id
                )
                in tied_ids
            ):
                selection.selected_user_id = None
                selection.selected_by_user_id = None
                selection.selected_at = None
                selection.reason = None

            selection.is_tie = True
            selection.tied_user_ids = tied_ids

        self.db.flush()

    def get_employee_of_month(
        self,
        current_user,
        year: int,
        month: int,
    ) -> PmsEmployeeOfMonthResponse:
        # IMPORTANT:
        # `metrics` is a collection relationship. Using joinedload(metrics)
        # here makes SQLAlchemy produce duplicate parent rows and requires
        # Result.unique() before scalar consumption.
        #
        # selectinload(metrics) is a better fit here: the monthly records are
        # loaded once, then their metrics are fetched in a second IN query.
        # This keeps each PmsMonthlyRecord unique and prevents the EOM endpoint
        # from failing even when every employee has multiple metric rows.
        completed = list(
            self.db.scalars(
                select(PmsMonthlyRecord)
                .options(
                    joinedload(
                        PmsMonthlyRecord.user
                    ),
                    joinedload(
                        PmsMonthlyRecord.updated_by
                    ),
                    selectinload(
                        PmsMonthlyRecord.metrics
                    ),
                )
                .where(
                    PmsMonthlyRecord.year == year,
                    PmsMonthlyRecord.month == month,
                    PmsMonthlyRecord.status
                    == PmsMonthlyStatus.COMPLETED,
                )
            )
        )

        if not completed:
            return PmsEmployeeOfMonthResponse(
                year=year,
                month=month,
            )

        top_score = max(
            float(record.final_score)
            for record in completed
        )

        top_records = [
            record
            for record in completed
            if float(record.final_score)
            == top_score
        ]

        candidates = [
            PmsEmployeeOfMonthCandidate(
                user_id=record.user_id,
                user_name=(
                    (
                        record.user.full_name
                        or record.user.email
                    )
                    if record.user
                    else ''
                ),
                final_score=float(
                    record.final_score
                ),
            )
            for record in top_records
        ]

        if len(top_records) == 1:
            winner = top_records[0]

            return PmsEmployeeOfMonthResponse(
                year=year,
                month=month,
                is_tie=False,
                candidates=candidates,
                winner=self._serialize_record(
                    winner,
                    winner.user,
                ),
            )

        selection = self.db.scalar(
            select(
                PmsEmployeeOfMonthSelection
            ).where(
                PmsEmployeeOfMonthSelection.year
                == year,
                PmsEmployeeOfMonthSelection.month
                == month,
            )
        )

        if (
            selection
            and selection.selected_user_id
        ):
            winner = next(
                (
                    record
                    for record in top_records
                    if record.user_id
                    == selection.selected_user_id
                ),
                None,
            )

            if winner:
                return PmsEmployeeOfMonthResponse(
                    year=year,
                    month=month,
                    is_tie=True,
                    candidates=candidates,
                    winner=self._serialize_record(
                        winner,
                        winner.user,
                    ),
                )

        return PmsEmployeeOfMonthResponse(
            year=year,
            month=month,
            is_tie=True,
            candidates=candidates,
            winner=None,
        )

    def resolve_employee_of_month(
        self,
        current_user,
        payload: PmsEmployeeOfMonthResolveRequest,
    ) -> PmsEmployeeOfMonthResponse:
        self._require_admin(
            current_user
        )

        selection = self.db.scalar(
            select(
                PmsEmployeeOfMonthSelection
            ).where(
                PmsEmployeeOfMonthSelection.year
                == payload.year,
                PmsEmployeeOfMonthSelection.month
                == payload.month,
            )
        )

        if (
            not selection
            or not selection.is_tie
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                'There is no tie to resolve for this month',
            )

        tied_ids = set(
            selection.tied_user_ids
            or []
        )

        if (
            str(payload.selected_user_id)
            not in tied_ids
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                (
                    'Selected employee is not among '
                    'the tied top scorers'
                ),
            )

        selection.selected_user_id = (
            payload.selected_user_id
        )

        selection.selected_by_user_id = (
            current_user.id
        )

        selection.selected_at = (
            datetime.now(UTC)
        )

        selection.reason = payload.reason

        self.db.flush()

        self.audit.log(
            action='PMS_EMPLOYEE_OF_MONTH_SELECTED',
            user_id=current_user.id,
            entity_type='PMS_EMPLOYEE_OF_MONTH',
            category='PMS_MANAGEMENT',
            metadata={
                'year': payload.year,
                'month': payload.month,
                'selected_user_id': str(
                    payload.selected_user_id
                ),
                'reason': payload.reason,
            },
        )

        self.db.commit()

        return self.get_employee_of_month(
            current_user,
            payload.year,
            payload.month,
        )

    # ------------------------------------------------------------------
    # Authorization helpers
    # ------------------------------------------------------------------
    def _require_admin(
        self,
        current_user,
    ) -> None:
        if not is_admin(
            current_user
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                'Only admins can perform this action',
            )

    def _require_view_all(
        self,
        current_user,
    ) -> None:
        if not can_manage_operations(
            current_user
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                (
                    'Only admins and operations managers '
                    'can view all employees'
                ),
            )

    def _authorize_self_or_privileged(
        self,
        current_user,
        user_id: UUID,
    ) -> None:
        if (
            is_support_agent(current_user)
            and str(current_user.id)
            != str(user_id)
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                'Agents can only view their own PMS record',
            )
