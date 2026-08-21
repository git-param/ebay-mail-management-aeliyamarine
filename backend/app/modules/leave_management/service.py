import calendar
from datetime import UTC, date, datetime, time
from math import ceil
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import is_admin, is_support_agent
from app.models.user import User
from app.modules.leave_management.models import LeaveBalanceLedger, LeavePolicy, LeaveRequest
from app.modules.leave_management.schemas import (
    DAY_PARTS,
    INSTANCE_KINDS,
    SHORT_PATTERNS,
    LeavePolicyUpdate,
    LeaveAdminSummaryUpdate,
    LeaveRequestCreate,
    LeaveReviewRequest,
)
from app.services.audit_service import AuditService


LEAVE_SYSTEM_START = date(2026, 8, 1)
AGENT_ROLE_NAME = 'Support Agent'
ADH_LEDGER_ENTRY_TYPE = 'ADH_OVERRIDE'
PAID_SUMMARY_LEDGER_ENTRY_TYPE = 'PAID_SUMMARY_OVERRIDE'
UNPAID_SUMMARY_LEDGER_ENTRY_TYPE = 'UNPAID_SUMMARY_OVERRIDE'


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
        if not is_support_agent(current_user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, 'Leave requests are available only for agent users')
        policy = self.get_policy()
        end_date = payload.end_date or payload.start_date
        if payload.start_date < LEAVE_SYSTEM_START or end_date < LEAVE_SYSTEM_START:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Leave tracking starts on August 1, 2026')
        if end_date < payload.start_date:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'End date cannot be before start date')
        self._ensure_no_overlapping_request(current_user.id, payload.start_date, end_date)

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
            request.duration_days = 0.5 if day_part == 'HALF' else self._leave_days_excluding_sundays(payload.start_date, end_date)
            if float(request.duration_days) <= 0:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Paid leave cannot be requested for Sundays only')

        elif payload.leave_type == 'INSTANCE':
            kind = (payload.instance_kind or '').strip().upper()
            if kind not in INSTANCE_KINDS:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Instance leave must be LATE_ARRIVAL or EARLY_DEPARTURE')
            if payload.start_date != end_date:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Instance leave must be a single date')
            request.instance_kind = kind

        else:
            pattern = (payload.short_leave_pattern or '').strip().upper()
            if pattern not in SHORT_PATTERNS:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Invalid short leave pattern')
            if payload.start_date != end_date:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Short leave must be a single date')
            self._ensure_short_leave_slot_available(current_user.id, payload.start_date.year, payload.start_date.month, policy)
            request.short_leave_pattern = pattern

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
            statement = statement.where(LeaveRequest.user.has(User.role.has(name=AGENT_ROLE_NAME)))
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
        if not is_support_agent(user):
            raise HTTPException(status.HTTP_404_NOT_FOUND, 'Leave data is available only for agent users')

        policy = self.get_policy()
        paid_accrued = self._paid_accrued_until(policy, year, month)
        paid_used = self._paid_used_until(user_id, year, month)
        # Admin summary edits for months without leave rows are stored in the
        # existing leave balance ledger. Include those paid totals here so the
        # balance view reflects the admin-entered summary even before any leave
        # request exists for that month.
        paid_used += self._paid_summary_override_used_until(user_id, year, month)
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
        users_statement = self._agent_users_statement()
        if user_id:
            users_statement = users_statement.where(User.id == user_id)
        return [self.get_balance(current_user, user.id, year, month) for user in self.db.scalars(users_statement)]

    def list_admin_summary(self, current_user, year: int, month: int) -> list[dict]:
        self._require_admin(current_user)
        users = list(self.db.scalars(self._agent_users_statement()))
        rows = []
        for user in users:
            actual = self._actual_admin_summary_for_user(user.id, year, month)
            has_paid_requests = self._has_approved_paid_requests(user.id, year, month)
            if not has_paid_requests:
                actual['paid_leaves'] = self._monthly_ledger_value(user.id, year, month, PAID_SUMMARY_LEDGER_ENTRY_TYPE)
                actual['unpaid_leaves'] = self._monthly_ledger_value(user.id, year, month, UNPAID_SUMMARY_LEDGER_ENTRY_TYPE)
            rows.append({
                'user_id': user.id,
                'employee': user.full_name or user.email,
                'year': year,
                'month': month,
                'paid_leaves': round(float(actual.get('paid_leaves', 0)), 2),
                'unpaid_leaves': round(float(actual.get('unpaid_leaves', 0)), 2),
                'adh': int(self._adh_override(user.id, year, month)),
                'is_overridden': (
                    self._has_monthly_ledger_value(user.id, year, month, PAID_SUMMARY_LEDGER_ENTRY_TYPE)
                    or self._has_monthly_ledger_value(user.id, year, month, UNPAID_SUMMARY_LEDGER_ENTRY_TYPE)
                    or self._has_monthly_ledger_value(user.id, year, month, ADH_LEDGER_ENTRY_TYPE)
                ),
            })
        return rows

    def update_admin_summary(self, current_user, payload: LeaveAdminSummaryUpdate) -> list[dict]:
        self._require_admin(current_user)
        for item in payload.items:
            user = self.db.get(User, item.user_id)
            if not user:
                raise HTTPException(status.HTTP_404_NOT_FOUND, 'User not found')
            if not is_support_agent(user):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Leave summary can be updated only for agent users')
            self._apply_paid_summary_correction(
                current_user,
                item.user_id,
                payload.year,
                payload.month,
                float(item.paid_leaves),
                float(item.unpaid_leaves),
            )
            self._set_adh_override(current_user, item.user_id, payload.year, payload.month, int(item.adh))

        self.db.commit()
        return self.list_admin_summary(current_user, payload.year, payload.month)

    def pms_impact_for_user_month(self, user_id: UUID, year: int, month: int) -> dict:
        policy = self.get_policy()
        start, end = self._month_range(year, month)
        approved = list(self.db.scalars(select(LeaveRequest).where(
            LeaveRequest.user_id == user_id,
            LeaveRequest.status == 'APPROVED',
            LeaveRequest.start_date >= start,
            LeaveRequest.start_date <= end,
        )))
        approved_paid = [item for item in approved if item.leave_type == 'PAID']
        paid_deduction_count = sum(self._paid_pms_deduction_count(item) for item in approved_paid)
        if not approved_paid:
            # When an admin edits a summary month that has no leave request rows,
            # paid/unpaid totals are represented by monthly ledger overrides.
            # Unpaid leave is already the amount beyond the 1.5 monthly paid
            # allowance, and each excess full or half leave occurrence deducts
            # one PMS attendance point, so partial unpaid totals are rounded up.
            paid_deduction_count = int(ceil(max(self._monthly_ledger_value(user_id, year, month, UNPAID_SUMMARY_LEDGER_ENTRY_TYPE), 0)))

        approved_instances = [item for item in approved if item.leave_type == 'INSTANCE']
        approved_short = [item for item in approved if item.leave_type == 'SHORT']
        adh_count = self._adh_override(user_id, year, month)
        combined_adh_limit = int(policy.instance_limit) + int(policy.short_leave_limit)
        # ADH is maintained by admin from the summary table. It represents the
        # monthly short/instance count, while the allowed limits still come from
        # Admin Config. A PMS punctuality point is deducted only for counts above
        # those configured limits.
        punctuality_deduction_count = max(adh_count - combined_adh_limit, 0)
        return {
            'user_id': user_id,
            'year': year,
            'month': month,
            'attendance_deduction': round(paid_deduction_count * float(policy.attendance_deduction_per_excess), 2),
            'punctuality_deduction': round(punctuality_deduction_count * float(policy.punctuality_deduction_per_extra_instance), 2),
            'excess_paid_occurrences': paid_deduction_count,
            'approved_instances': len(approved_instances),
            'extra_instances': max(adh_count - combined_adh_limit, 0),
            'approved_short': len(approved_short),
            'extra_short': 0,
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
            request.pms_attendance_deduction = round(self._paid_pms_deduction_count(request) * float(policy.attendance_deduction_per_excess), 2)

        elif request.leave_type == 'INSTANCE':
            # Instance leave uses the Admin-configured monthly count limit.
            # The first `policy.instance_limit` approved requests have no PMS
            # impact. Once that configured limit is already reached, approving
            # another instance request deducts one punctuality PMS point using
            # the Admin-configured deduction value.
            existing_count = self._approved_count(request.user_id, month_year, month, 'INSTANCE')
            if existing_count >= int(policy.instance_limit):
                request.pms_punctuality_deduction = float(policy.punctuality_deduction_per_extra_instance)

        elif request.leave_type == 'SHORT':
            # Short leave uses the Admin-configured monthly count limit. The
            # first `policy.short_leave_limit` approved requests have no PMS
            # impact. Every approved short leave after that configured limit
            # deducts one punctuality PMS point using the Admin-configured
            # deduction value.
            if self._approved_count(request.user_id, month_year, month, 'SHORT') >= int(policy.short_leave_limit):
                request.pms_punctuality_deduction = float(policy.punctuality_deduction_per_extra_instance)

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

    def _paid_summary_override_used_until(self, user_id: UUID, year: int, month: int) -> float:
        return float(self.db.scalar(select(func.coalesce(func.sum(LeaveBalanceLedger.amount), 0)).where(
            LeaveBalanceLedger.user_id == user_id,
            LeaveBalanceLedger.entry_type == PAID_SUMMARY_LEDGER_ENTRY_TYPE,
            (LeaveBalanceLedger.year * 100 + LeaveBalanceLedger.month) <= (year * 100 + month),
        )) or 0)

    def _paid_available_at_month_start(self, policy: LeavePolicy, user_id: UUID, year: int, month: int) -> float:
        previous_year = year if month > 1 else year - 1
        previous_month = month - 1 if month > 1 else 12
        accrued = self._paid_accrued_until(policy, year, month)
        used_before_month = self._paid_used_until(user_id, previous_year, previous_month)
        used_before_month += self._paid_summary_override_used_until(user_id, previous_year, previous_month)
        return max(accrued - used_before_month, 0)

    def _approved_count(self, user_id: UUID, year: int, month: int, leave_type: str) -> int:
        start, end = self._month_range(year, month)
        return int(self.db.scalar(select(func.count()).select_from(LeaveRequest).where(
            LeaveRequest.user_id == user_id,
            LeaveRequest.leave_type == leave_type,
            LeaveRequest.status == 'APPROVED',
            LeaveRequest.start_date >= start,
            LeaveRequest.start_date <= end,
        )) or 0)

    def _actual_admin_summary_for_user(self, user_id: UUID, year: int, month: int) -> dict:
        start, end = self._month_range(year, month)
        approved = list(self.db.scalars(select(LeaveRequest).where(
            LeaveRequest.user_id == user_id,
            LeaveRequest.status == 'APPROVED',
            LeaveRequest.start_date >= start,
            LeaveRequest.start_date <= end,
        )))
        return {
            'paid_leaves': sum(float(item.paid_days or 0) for item in approved if item.leave_type == 'PAID'),
            'unpaid_leaves': sum(float(item.excess_days or 0) for item in approved if item.leave_type == 'PAID'),
        }

    def _has_approved_paid_requests(self, user_id: UUID, year: int, month: int) -> bool:
        start, end = self._month_range(year, month)
        return bool(self.db.scalar(select(LeaveRequest.id).where(
            LeaveRequest.user_id == user_id,
            LeaveRequest.status == 'APPROVED',
            LeaveRequest.leave_type == 'PAID',
            LeaveRequest.start_date >= start,
            LeaveRequest.start_date <= end,
        ).limit(1)))

    def _apply_paid_summary_correction(
        self,
        current_user,
        user_id: UUID,
        year: int,
        month: int,
        paid_total: float,
        unpaid_total: float,
    ) -> None:
        paid_requests = self._approved_requests_for_month(user_id, year, month, 'PAID')
        if not paid_requests:
            self._set_monthly_ledger_value(
                current_user,
                user_id,
                year,
                month,
                PAID_SUMMARY_LEDGER_ENTRY_TYPE,
                paid_total,
                'Admin paid leave monthly override',
            )
            self._set_monthly_ledger_value(
                current_user,
                user_id,
                year,
                month,
                UNPAID_SUMMARY_LEDGER_ENTRY_TYPE,
                unpaid_total,
                'Admin unpaid leave monthly override',
            )
            return

        self._clear_monthly_ledger_value(user_id, year, month, PAID_SUMMARY_LEDGER_ENTRY_TYPE)
        self._clear_monthly_ledger_value(user_id, year, month, UNPAID_SUMMARY_LEDGER_ENTRY_TYPE)

        paid_values = self._distribute_summary_total(paid_requests, paid_total)
        unpaid_values = self._distribute_summary_total(paid_requests, unpaid_total)
        for request, paid_days, excess_days in zip(paid_requests, paid_values, unpaid_values, strict=False):
            request.paid_days = paid_days
            request.excess_days = excess_days
            self._upsert_paid_ledger(current_user, request, year, month)

        self._recalculate_paid_pms_for_month(current_user, user_id, year, month)

    def _upsert_paid_ledger(self, current_user, request: LeaveRequest, year: int, month: int) -> None:
        ledger = self.db.scalar(select(LeaveBalanceLedger).where(
            LeaveBalanceLedger.source_request_id == request.id,
            LeaveBalanceLedger.entry_type == 'PAID_DEDUCTION',
        ))
        paid_days = float(request.paid_days or 0)
        if paid_days <= 0:
            if ledger:
                self.db.delete(ledger)
            return
        if not ledger:
            ledger = LeaveBalanceLedger(
                user_id=request.user_id,
                year=year,
                month=month,
                entry_type='PAID_DEDUCTION',
                source_request_id=request.id,
                note='Paid leave summary correction',
                created_by_user_id=current_user.id,
            )
            self.db.add(ledger)
        ledger.amount = -paid_days

    def _distribute_summary_total(self, requests: list[LeaveRequest], total: float) -> list[float]:
        remaining = round(float(total), 2)
        values: list[float] = []
        for index, request in enumerate(requests):
            if index == len(requests) - 1:
                value = remaining
            else:
                value = min(round(float(request.duration_days or 0), 2), remaining)
            values.append(round(value, 2))
            remaining = round(max(remaining - value, 0), 2)
        return values

    def _recalculate_paid_pms_for_month(self, current_user, user_id: UUID, year: int, month: int) -> None:
        policy = self.get_policy()
        paid_requests = self._approved_requests_for_month(user_id, year, month, 'PAID')
        for request in paid_requests:
            request.pms_attendance_deduction = round(self._paid_pms_deduction_count(request) * float(policy.attendance_deduction_per_excess), 2)
        self._recalculate_pms_after_leave(current_user, user_id, year, month)

    def _paid_pms_deduction_count(self, request: LeaveRequest) -> int:
        return int(ceil(max(float(request.excess_days or 0), 0)))

    def _monthly_ledger_value(self, user_id: UUID, year: int, month: int, entry_type: str) -> float:
        ledger = self._monthly_ledger_entry(user_id, year, month, entry_type)
        return float(ledger.amount) if ledger else 0.0

    def _has_monthly_ledger_value(self, user_id: UUID, year: int, month: int, entry_type: str) -> bool:
        return self._monthly_ledger_entry(user_id, year, month, entry_type) is not None

    def _monthly_ledger_entry(self, user_id: UUID, year: int, month: int, entry_type: str) -> LeaveBalanceLedger | None:
        ledgers = list(self.db.scalars(select(LeaveBalanceLedger).where(
            LeaveBalanceLedger.user_id == user_id,
            LeaveBalanceLedger.year == year,
            LeaveBalanceLedger.month == month,
            LeaveBalanceLedger.entry_type == entry_type,
            LeaveBalanceLedger.source_request_id.is_(None),
        ).order_by(LeaveBalanceLedger.created_at.asc())))
        ledger = ledgers[0] if ledgers else None
        for duplicate in ledgers[1:]:
            self.db.delete(duplicate)
        return ledger

    def _set_monthly_ledger_value(
        self,
        current_user,
        user_id: UUID,
        year: int,
        month: int,
        entry_type: str,
        amount: float,
        note: str,
    ) -> None:
        ledger = self._monthly_ledger_entry(user_id, year, month, entry_type)
        if not ledger:
            ledger = LeaveBalanceLedger(
                user_id=user_id,
                year=year,
                month=month,
                entry_type=entry_type,
                source_request_id=None,
                note=note,
                created_by_user_id=current_user.id,
            )
            self.db.add(ledger)
        ledger.amount = round(float(amount), 2)
        ledger.note = note
        ledger.created_by_user_id = current_user.id

    def _clear_monthly_ledger_value(self, user_id: UUID, year: int, month: int, entry_type: str) -> None:
        ledger = self._monthly_ledger_entry(user_id, year, month, entry_type)
        if ledger:
            self.db.delete(ledger)

    def _adh_override(self, user_id: UUID, year: int, month: int) -> int:
        ledger = self.db.scalar(select(LeaveBalanceLedger).where(
            LeaveBalanceLedger.user_id == user_id,
            LeaveBalanceLedger.year == year,
            LeaveBalanceLedger.month == month,
            LeaveBalanceLedger.entry_type == ADH_LEDGER_ENTRY_TYPE,
        ).order_by(LeaveBalanceLedger.created_at.desc()))
        return int(float(ledger.amount)) if ledger else 0

    def _set_adh_override(self, current_user, user_id: UUID, year: int, month: int, adh: int) -> None:
        ledgers = list(self.db.scalars(select(LeaveBalanceLedger).where(
            LeaveBalanceLedger.user_id == user_id,
            LeaveBalanceLedger.year == year,
            LeaveBalanceLedger.month == month,
            LeaveBalanceLedger.entry_type == ADH_LEDGER_ENTRY_TYPE,
        ).order_by(LeaveBalanceLedger.created_at.asc())))
        ledger = ledgers[0] if ledgers else None
        for duplicate in ledgers[1:]:
            self.db.delete(duplicate)
        if not ledger:
            ledger = LeaveBalanceLedger(
                user_id=user_id,
                year=year,
                month=month,
                entry_type=ADH_LEDGER_ENTRY_TYPE,
                source_request_id=None,
                note='Admin ADH monthly override',
                created_by_user_id=current_user.id,
            )
            self.db.add(ledger)
        ledger.amount = int(adh)
        ledger.created_by_user_id = current_user.id

    def _agent_users_statement(self):
        return select(User).where(User.is_active.is_(True), User.role.has(name=AGENT_ROLE_NAME)).order_by(User.full_name.asc())

    def _approved_requests_for_month(self, user_id: UUID, year: int, month: int, leave_type: str | None = None) -> list[LeaveRequest]:
        start, end = self._month_range(year, month)
        statement = select(LeaveRequest).where(
            LeaveRequest.user_id == user_id,
            LeaveRequest.status == 'APPROVED',
            LeaveRequest.start_date >= start,
            LeaveRequest.start_date <= end,
        )
        if leave_type:
            statement = statement.where(LeaveRequest.leave_type == leave_type)
        return list(self.db.scalars(statement.order_by(LeaveRequest.created_at.asc(), LeaveRequest.id.asc())))

    def _paid_pms_deductions_by_request(self, policy: LeavePolicy, requests: list[LeaveRequest], paid_allowance: float | None = None) -> dict[UUID, int]:
        paid_allowance = float(policy.paid_leave_per_month if paid_allowance is None else paid_allowance)
        deductions: dict[UUID, int] = {}

        # Paid leave allowance is 1.5 days per month from Admin Config, plus
        # any carry-forward balance available to the employee. Sundays are
        # excluded before this point, so full-day requests consume only their
        # non-Sunday duration and half-day requests consume 0.5 day. PMS
        # deduction is based on excess leave days rounded up to whole PMS
        # points: once the allowance is exhausted, any remaining full or half
        # day portion costs one attendance PMS point. Example: a 3-day paid
        # request with 1.5 paid days available has 1.5 excess days, so it
        # deducts ceil(1.5) = 2 PMS points. Requests are evaluated in creation
        # order, not leave-date order, so a later-applied half-day for an earlier
        # date cannot consume allowance that an earlier request already used.
        for request in sorted(requests, key=lambda item: (item.created_at, item.id)):
            if request.leave_type != 'PAID':
                continue

            requested_days = 0.5 if (request.day_part or '').upper() == 'HALF' else float(request.duration_days or 0)
            excess_days = max(requested_days - paid_allowance, 0)
            if excess_days > 0:
                deductions[request.id] = int(ceil(excess_days))
            paid_allowance = max(paid_allowance - requested_days, 0)

        return deductions

    def _ensure_short_leave_slot_available(self, user_id: UUID, year: int, month: int, policy: LeavePolicy) -> None:
        # Short leave is capped by the Admin-configured monthly limit. Pending
        # requests reserve a slot until they are rejected/cancelled; approved
        # requests consume a slot permanently for that month. Therefore, when
        # the active pending+approved count has reached `policy.short_leave_limit`,
        # the employee cannot request another short leave.
        active_count = self._active_count(user_id, year, month, 'SHORT')
        if active_count >= int(policy.short_leave_limit):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f'Monthly short leave limit is already used. You can request another short leave only if an existing pending short leave is rejected or cancelled.',
            )

    def _ensure_no_overlapping_request(self, user_id: UUID, start_date: date, end_date: date) -> None:
        # Overlap validation is enforced in the backend so it cannot be bypassed
        # by a custom client. Pending and approved requests reserve their date
        # ranges; rejected and cancelled requests do not. Date ranges overlap
        # when the new start is on/before the existing end and the new end is
        # on/after the existing start, covering partial and exact collisions
        # such as 19-20, 15-21, 21-25, and 19-22 against an existing 19-22.
        overlap = self.db.scalar(select(LeaveRequest).where(
            LeaveRequest.user_id == user_id,
            LeaveRequest.status.in_(['PENDING', 'APPROVED']),
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        ).order_by(LeaveRequest.start_date.asc()))
        if overlap:
            existing = self._format_date_range(overlap.start_date, overlap.end_date)
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f'You already have a leave request overlapping these dates ({existing}). Please select different dates.',
            )

    def _active_count(self, user_id: UUID, year: int, month: int, leave_type: str) -> int:
        start, end = self._month_range(year, month)
        return int(self.db.scalar(select(func.count()).select_from(LeaveRequest).where(
            LeaveRequest.user_id == user_id,
            LeaveRequest.leave_type == leave_type,
            LeaveRequest.status.in_(['PENDING', 'APPROVED']),
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

    def _leave_days_excluding_sundays(self, start: date, end: date) -> float:
        # Sundays are not counted as leave days and therefore do not consume
        # paid leave allowance or produce PMS deductions. The stored date range
        # is kept intact for visibility/overlap checks, but duration/PMS uses
        # this non-Sunday count.
        current = start
        days = 0
        while current <= end:
            if current.weekday() != 6:
                days += 1
            current = date.fromordinal(current.toordinal() + 1)
        return float(days)

    def _month_range(self, year: int, month: int) -> tuple[date, date]:
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])

    def _format_date_range(self, start: date, end: date) -> str:
        if start == end:
            return str(start.day)
        return f'{start.day}-{end.day}'
