import calendar
from datetime import UTC, date, datetime, time
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import is_admin
from app.models.user import User
from app.modules.leave_management.models import LeaveBalanceLedger, LeavePolicy, LeaveRequest
from app.modules.leave_management.schemas import (
    DAY_PARTS,
    INSTANCE_KINDS,
    SHORT_PATTERNS,
    LeavePolicyUpdate,
    LeaveRequestCreate,
    LeaveReviewRequest,
)
from app.services.audit_service import AuditService


LEAVE_SYSTEM_START = date(2026, 8, 1)


class LeaveManagementService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    def get_policy(self) -> LeavePolicy:
        policy = self.db.scalar(select(LeavePolicy).order_by(LeavePolicy.created_at.desc()))
        if policy:
            return policy

        policy = LeavePolicy(effective_from=LEAVE_SYSTEM_START)
        self.db.add(policy)
        self.db.flush()
        return policy

    def update_policy(self, current_user, payload: LeavePolicyUpdate) -> LeavePolicy:
        self._require_admin(current_user)
        policy = self.get_policy()
        before = self._policy_snapshot(policy)
        data = payload.model_dump(exclude_unset=True)

        if data.get('short_leave_over_limit_action') and data['short_leave_over_limit_action'] != 'BLOCK':
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Only BLOCK is supported for short leave over-limit handling')

        if 'office_start_time' in data and 'office_end_time' in data and data['office_start_time'] >= data['office_end_time']:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Office start time must be before office end time')

        for key, value in data.items():
            setattr(policy, key, value)

        policy.updated_by_user_id = current_user.id
        self.db.flush()

        self.audit.log(
            action='LEAVE_POLICY_UPDATED',
            user_id=current_user.id,
            entity_type='LEAVE_POLICY',
            entity_id=policy.id,
            category='LEAVE_MANAGEMENT',
            metadata={'old': before, 'new': self._policy_snapshot(policy)},
        )
        self.db.commit()
        self.db.refresh(policy)
        return policy

    def create_request(self, current_user, payload: LeaveRequestCreate) -> LeaveRequest:
        policy = self.get_policy()
        end_date = payload.end_date or payload.start_date
        if payload.start_date < LEAVE_SYSTEM_START or end_date < LEAVE_SYSTEM_START:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Leave tracking starts on August 1, 2026')
        if end_date < payload.start_date:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'End date cannot be before start date')

        request = LeaveRequest(
            user_id=current_user.id,
            leave_type=payload.leave_type,
            start_date=payload.start_date,
            end_date=end_date,
            reason=payload.reason.strip(),
            status='PENDING',
        )

        if payload.leave_type == 'PAID':
            day_part = (payload.day_part or 'FULL').strip().upper()
            if day_part not in DAY_PARTS:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Paid leave day_part must be FULL or HALF')
            if day_part == 'HALF' and payload.start_date != end_date:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Half-day paid leave must be a single date')
            request.day_part = day_part
            request.duration_days = 0.5 if day_part == 'HALF' else self._inclusive_days(payload.start_date, end_date)

        elif payload.leave_type == 'INSTANCE':
            kind = (payload.instance_kind or '').strip().upper()
            if kind not in INSTANCE_KINDS:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Instance leave must be LATE_ARRIVAL or EARLY_DEPARTURE')
            if payload.start_date != end_date:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Instance leave must be a single date')
            minutes = self._minutes_from_payload(payload)
            if minutes > int(policy.instance_max_minutes):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f'Instance leave cannot exceed {policy.instance_max_minutes} minutes')
            self._validate_instance_timing(policy, kind, payload.start_time, payload.end_time)
            request.instance_kind = kind
            request.start_time = payload.start_time
            request.end_time = payload.end_time

        else:
            pattern = (payload.short_leave_pattern or '').strip().upper()
            if pattern not in SHORT_PATTERNS:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Invalid short leave pattern')
            if payload.start_date != end_date:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Short leave must be a single date')
            minutes = self._minutes_from_payload(payload)
            if minutes > int(policy.short_leave_max_minutes):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f'Short leave cannot exceed {policy.short_leave_max_minutes} minutes')
            self._validate_short_timing(policy, payload.start_time, payload.end_time)
            balance = self.get_balance(current_user, current_user.id, payload.start_date.year, payload.start_date.month)
            if balance['short_used'] >= int(policy.short_leave_limit):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Monthly short leave limit is already used')
            request.short_leave_pattern = pattern
            request.start_time = payload.start_time
            request.end_time = payload.end_time

        self.db.add(request)
        self.db.flush()
        self.audit.log(
            action='LEAVE_REQUEST_CREATED',
            user_id=current_user.id,
            entity_type='LEAVE_REQUEST',
            entity_id=request.id,
            category='LEAVE_MANAGEMENT',
            metadata={'leave_type': request.leave_type, 'start_date': request.start_date.isoformat(), 'end_date': request.end_date.isoformat()},
        )
        self.db.commit()
        self.db.refresh(request)
        return request

    def list_requests(
        self,
        current_user,
        *,
        user_id: UUID | None = None,
        leave_type: str | None = None,
        status_filter: str | None = None,
        year: int | None = None,
        month: int | None = None,
    ) -> list[LeaveRequest]:
        statement = select(LeaveRequest).options(joinedload(LeaveRequest.user), joinedload(LeaveRequest.reviewed_by))
        if is_admin(current_user):
            if user_id:
                statement = statement.where(LeaveRequest.user_id == user_id)
        else:
            statement = statement.where(LeaveRequest.user_id == current_user.id)

        if leave_type:
            statement = statement.where(LeaveRequest.leave_type == leave_type.upper())
        if status_filter:
            statement = statement.where(LeaveRequest.status == status_filter.upper())
        if year and month:
            start, end = self._month_range(year, month)
            statement = statement.where(LeaveRequest.start_date >= start, LeaveRequest.start_date <= end)

        return list(self.db.scalars(statement.order_by(LeaveRequest.created_at.desc())))

    def review_request(self, current_user, request_id: UUID, payload: LeaveReviewRequest) -> LeaveRequest:
        self._require_admin(current_user)
        request = self.db.scalar(select(LeaveRequest).where(LeaveRequest.id == request_id).with_for_update())
        if not request:
            raise HTTPException(status.HTTP_404_NOT_FOUND, 'Leave request not found')
        if request.status != 'PENDING':
            raise HTTPException(status.HTTP_409_CONFLICT, 'Only pending leave requests can be reviewed')

        if payload.status == 'REJECTED':
            request.status = 'REJECTED'
            request.reviewed_by_user_id = current_user.id
            request.reviewed_at = datetime.now(UTC)
            request.review_note = payload.review_note
            self.audit.log(
                action='LEAVE_REQUEST_REJECTED',
                user_id=current_user.id,
                entity_type='LEAVE_REQUEST',
                entity_id=request.id,
                category='LEAVE_MANAGEMENT',
                metadata={'employee_user_id': str(request.user_id), 'review_note': payload.review_note},
            )
            self.db.commit()
            self.db.refresh(request)
            return request

        self._approve_request(current_user, request, payload.review_note)
        self.db.commit()
        self.db.refresh(request)
        return request

    def cancel_request(self, current_user, request_id: UUID) -> LeaveRequest:
        request = self.db.get(LeaveRequest, request_id)
        if not request:
            raise HTTPException(status.HTTP_404_NOT_FOUND, 'Leave request not found')
        if not is_admin(current_user) and request.user_id != current_user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, 'Agents can only cancel their own requests')
        if request.status != 'PENDING':
            raise HTTPException(status.HTTP_409_CONFLICT, 'Only pending requests can be cancelled')
        request.status = 'CANCELLED'
        self.audit.log(
            action='LEAVE_REQUEST_CANCELLED',
            user_id=current_user.id,
            entity_type='LEAVE_REQUEST',
            entity_id=request.id,
            category='LEAVE_MANAGEMENT',
            metadata={'employee_user_id': str(request.user_id)},
        )
        self.db.commit()
        self.db.refresh(request)
        return request

    def get_balance(self, current_user, user_id: UUID, year: int, month: int) -> dict:
        self._authorize_self_or_admin(current_user, user_id)
        user = self.db.get(User, user_id)
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, 'User not found')

        policy = self.get_policy()
        paid_accrued = self._paid_accrued_until(policy, year, month)
        paid_used = self._paid_used_until(user_id, year, month)
        impact = self.pms_impact_for_user_month(user_id, year, month)
        short_used = self._approved_count(user_id, year, month, 'SHORT')
        instance_used = self._approved_count(user_id, year, month, 'INSTANCE')
        return {
            'user_id': user.id,
            'user_name': user.full_name or user.email,
            'user_email': user.email,
            'year': year,
            'month': month,
            'paid_accrued': round(paid_accrued, 2),
            'paid_used': round(paid_used, 2),
            'paid_available': round(max(paid_accrued - paid_used, 0), 2),
            'excess_paid_occurrences': impact['excess_paid_occurrences'],
            'instance_used': instance_used,
            'instance_remaining': max(int(policy.instance_limit) - instance_used, 0),
            'short_used': short_used,
            'short_remaining': max(int(policy.short_leave_limit) - short_used, 0),
            'pms_attendance_deduction': impact['attendance_deduction'],
            'pms_punctuality_deduction': impact['punctuality_deduction'],
        }

    def list_balances(self, current_user, year: int, month: int, user_id: UUID | None = None) -> list[dict]:
        if not is_admin(current_user):
            return [self.get_balance(current_user, current_user.id, year, month)]
        users_statement = select(User).where(User.is_active.is_(True)).order_by(User.full_name.asc())
        if user_id:
            users_statement = users_statement.where(User.id == user_id)
        return [self.get_balance(current_user, user.id, year, month) for user in self.db.scalars(users_statement)]

    def pms_impact_for_user_month(self, user_id: UUID, year: int, month: int) -> dict:
        policy = self.get_policy()
        start, end = self._month_range(year, month)
        approved = list(self.db.scalars(select(LeaveRequest).where(
            LeaveRequest.user_id == user_id,
            LeaveRequest.status == 'APPROVED',
            LeaveRequest.start_date >= start,
            LeaveRequest.start_date <= end,
        )))
        excess_paid = [item for item in approved if item.leave_type == 'PAID' and float(item.excess_days or 0) > 0]
        approved_instances = [item for item in approved if item.leave_type == 'INSTANCE']
        extra_instances = max(len(approved_instances) - int(policy.instance_limit), 0)
        return {
            'user_id': user_id,
            'year': year,
            'month': month,
            'attendance_deduction': round(len(excess_paid) * float(policy.attendance_deduction_per_excess), 2),
            'punctuality_deduction': round(extra_instances * float(policy.punctuality_deduction_per_extra_instance), 2),
            'excess_paid_occurrences': len(excess_paid),
            'approved_instances': len(approved_instances),
            'extra_instances': extra_instances,
        }

    def _approve_request(self, current_user, request: LeaveRequest, review_note: str | None) -> None:
        policy = self.get_policy()
        month_year = request.start_date.year
        month = request.start_date.month

        if request.leave_type == 'PAID':
            available = max(self._paid_accrued_until(policy, month_year, month) - self._paid_used_until(request.user_id, month_year, month), 0)
            requested = float(request.duration_days)
            request.paid_days = round(min(requested, available), 2)
            request.excess_days = round(max(requested - float(request.paid_days), 0), 2)
            if float(request.paid_days) > 0:
                ledger_exists = self.db.scalar(select(LeaveBalanceLedger).where(
                    LeaveBalanceLedger.source_request_id == request.id,
                    LeaveBalanceLedger.entry_type == 'PAID_DEDUCTION',
                ))
                if not ledger_exists:
                    ledger = LeaveBalanceLedger(
                        user_id=request.user_id,
                        year=month_year,
                        month=month,
                        entry_type='PAID_DEDUCTION',
                        amount=-float(request.paid_days),
                        source_request_id=request.id,
                        note='Paid leave approved',
                        created_by_user_id=current_user.id,
                    )
                    self.db.add(ledger)
                    self.audit.log(
                        action='LEAVE_BALANCE_CHANGED',
                        user_id=current_user.id,
                        entity_type='LEAVE_REQUEST',
                        entity_id=request.id,
                        category='LEAVE_MANAGEMENT',
                        metadata={'employee_user_id': str(request.user_id), 'amount': float(ledger.amount), 'entry_type': ledger.entry_type},
                    )
            if float(request.excess_days) > 0:
                request.pms_attendance_deduction = float(policy.attendance_deduction_per_excess)

        elif request.leave_type == 'INSTANCE':
            existing_count = self._approved_count(request.user_id, month_year, month, 'INSTANCE')
            if existing_count >= int(policy.instance_limit):
                request.pms_punctuality_deduction = float(policy.punctuality_deduction_per_extra_instance)

        elif request.leave_type == 'SHORT':
            if self._approved_count(request.user_id, month_year, month, 'SHORT') >= int(policy.short_leave_limit):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Monthly short leave limit is already used')

        request.status = 'APPROVED'
        request.reviewed_by_user_id = current_user.id
        request.reviewed_at = datetime.now(UTC)
        request.review_note = review_note
        self.db.flush()

        self.audit.log(
            action='LEAVE_REQUEST_APPROVED',
            user_id=current_user.id,
            entity_type='LEAVE_REQUEST',
            entity_id=request.id,
            category='LEAVE_MANAGEMENT',
            metadata={
                'employee_user_id': str(request.user_id),
                'paid_days': float(request.paid_days),
                'excess_days': float(request.excess_days),
                'pms_attendance_deduction': float(request.pms_attendance_deduction),
                'pms_punctuality_deduction': float(request.pms_punctuality_deduction),
            },
        )
        self._recalculate_pms_after_leave(current_user, request.user_id, month_year, month)

    def _recalculate_pms_after_leave(self, current_user, user_id: UUID, year: int, month: int) -> None:
        from app.modules.pms.service import PmsService

        changed = PmsService(self.db).apply_leave_impact_to_existing_record(user_id, year, month, current_user)
        if changed:
            self.audit.log(
                action='LEAVE_PMS_RECALCULATED',
                user_id=current_user.id,
                entity_type='PMS_MONTHLY_RECORD',
                entity_id=changed.id,
                category='LEAVE_MANAGEMENT',
                metadata={'employee_user_id': str(user_id), 'year': year, 'month': month},
            )

    def _paid_accrued_until(self, policy: LeavePolicy, year: int, month: int) -> float:
        if date(year, month, 1) < LEAVE_SYSTEM_START:
            return 0.0
        months = (year - LEAVE_SYSTEM_START.year) * 12 + (month - LEAVE_SYSTEM_START.month) + 1
        return max(months, 0) * float(policy.paid_leave_per_month)

    def _paid_used_until(self, user_id: UUID, year: int, month: int) -> float:
        return float(self.db.scalar(select(func.coalesce(func.sum(LeaveBalanceLedger.amount), 0)).where(
            LeaveBalanceLedger.user_id == user_id,
            LeaveBalanceLedger.entry_type == 'PAID_DEDUCTION',
            (LeaveBalanceLedger.year * 100 + LeaveBalanceLedger.month) <= (year * 100 + month),
        )) or 0) * -1

    def _approved_count(self, user_id: UUID, year: int, month: int, leave_type: str) -> int:
        start, end = self._month_range(year, month)
        return int(self.db.scalar(select(func.count()).select_from(LeaveRequest).where(
            LeaveRequest.user_id == user_id,
            LeaveRequest.leave_type == leave_type,
            LeaveRequest.status == 'APPROVED',
            LeaveRequest.start_date >= start,
            LeaveRequest.start_date <= end,
        )) or 0)

    def _duration_minutes(self, start_time: time | None, end_time: time | None) -> int:
        if not start_time or not end_time:
            return 0
        start = start_time.hour * 60 + start_time.minute
        end = end_time.hour * 60 + end_time.minute
        return max(end - start, 0)

    def _minutes_from_payload(self, payload: LeaveRequestCreate) -> int:
        if not payload.start_time or not payload.end_time:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Start time and end time are required')

        minutes = self._duration_minutes(payload.start_time, payload.end_time)
        if minutes <= 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'End time must be after start time')
        return minutes

    def _validate_instance_timing(self, policy: LeavePolicy, kind: str, start_time: time | None, end_time: time | None) -> None:
        if kind == 'LATE_ARRIVAL' and end_time and end_time <= policy.office_start_time:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Late arrival must be after office start time')
        if kind == 'EARLY_DEPARTURE' and start_time and start_time >= policy.office_end_time:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Early departure must be before office end time')

    def _validate_short_timing(self, policy: LeavePolicy, start_time: time | None, end_time: time | None) -> None:
        if start_time and start_time < policy.office_start_time:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Short leave cannot start before office start time')
        if end_time and end_time > policy.office_end_time:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Short leave cannot end after office end time')

    def _serialize_request(self, item: LeaveRequest) -> dict:
        return {
            'id': item.id,
            'user_id': item.user_id,
            'user_name': (item.user.full_name or item.user.email) if item.user else None,
            'user_email': item.user.email if item.user else None,
            'leave_type': item.leave_type,
            'day_part': item.day_part,
            'instance_kind': item.instance_kind,
            'short_leave_pattern': item.short_leave_pattern,
            'start_date': item.start_date,
            'end_date': item.end_date,
            'start_time': item.start_time,
            'end_time': item.end_time,
            'duration_days': float(item.duration_days),
            # Duration is derived from the employee-entered time range.
            # It is intentionally not persisted as a separate DB column.
            'duration_minutes': self._duration_minutes(item.start_time, item.end_time),
            'reason': item.reason,
            'status': item.status,
            'paid_days': float(item.paid_days),
            'excess_days': float(item.excess_days),
            'pms_attendance_deduction': float(item.pms_attendance_deduction),
            'pms_punctuality_deduction': float(item.pms_punctuality_deduction),
            'reviewed_by_user_id': item.reviewed_by_user_id,
            'reviewed_by_name': (item.reviewed_by.full_name or item.reviewed_by.email) if item.reviewed_by else None,
            'reviewed_at': item.reviewed_at,
            'review_note': item.review_note,
            'created_at': item.created_at,
            'updated_at': item.updated_at,
        }

    def serialize_request(self, item: LeaveRequest) -> dict:
        if not item.user:
            item.user = self.db.get(User, item.user_id)
        return self._serialize_request(item)

    def _policy_snapshot(self, policy: LeavePolicy) -> dict:
        return {
            'paid_leave_per_month': float(policy.paid_leave_per_month),
            'instance_limit': policy.instance_limit,
            'short_leave_limit': policy.short_leave_limit,
            'office_start_time': policy.office_start_time.isoformat(),
            'office_end_time': policy.office_end_time.isoformat(),
            'attendance_deduction_per_excess': float(policy.attendance_deduction_per_excess),
            'punctuality_deduction_per_extra_instance': float(policy.punctuality_deduction_per_extra_instance),
        }

    def _require_admin(self, current_user) -> None:
        if not is_admin(current_user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, 'Only admins can perform this action')

    def _authorize_self_or_admin(self, current_user, user_id: UUID) -> None:
        if not is_admin(current_user) and current_user.id != user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, 'Agents can only view their own leave data')

    def _inclusive_days(self, start: date, end: date) -> float:
        return float((end - start).days + 1)

    def _month_range(self, year: int, month: int) -> tuple[date, date]:
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])