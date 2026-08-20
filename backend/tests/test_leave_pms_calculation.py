from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.leave_management.service import LeaveManagementService


def paid_request(*, start_date: date, days: float, day_part: str = 'FULL', created_at: datetime | None = None):
    return SimpleNamespace(
        id=uuid4(),
        leave_type='PAID',
        day_part=day_part,
        start_date=start_date,
        created_at=created_at or datetime(2026, 8, start_date.day, tzinfo=UTC),
        duration_days=days,
    )


def test_paid_pms_deduction_rounds_partial_excess_days_up_to_whole_points():
    policy = SimpleNamespace(paid_leave_per_month=1.5)
    requests = [
        paid_request(start_date=date(2026, 8, 20), days=3),
    ]

    deductions = LeaveManagementService._paid_pms_deductions_by_request(None, policy, requests)

    assert sum(deductions.values()) == 2
    assert deductions[requests[0].id] == 2


def test_paid_pms_deduction_counts_each_full_and_half_request_when_allowance_is_exhausted():
    policy = SimpleNamespace(paid_leave_per_month=1.5)
    requests = [
        paid_request(start_date=date(2026, 8, 19), days=1),
        paid_request(start_date=date(2026, 8, 20), days=1),
        paid_request(start_date=date(2026, 8, 21), days=1),
        paid_request(start_date=date(2026, 8, 22), days=0.5, day_part='HALF'),
    ]

    deductions = LeaveManagementService._paid_pms_deductions_by_request(None, policy, requests, paid_allowance=0)

    assert sum(deductions.values()) == 4
    assert all(deduction == 1 for deduction in deductions.values())


def test_paid_pms_deduction_charges_half_day_once_when_allowance_is_exhausted():
    policy = SimpleNamespace(paid_leave_per_month=3)
    requests = [
        paid_request(start_date=date(2026, 8, 1), days=3),
        paid_request(start_date=date(2026, 8, 4), days=0.5, day_part='HALF'),
    ]

    deductions = LeaveManagementService._paid_pms_deductions_by_request(None, policy, requests)

    assert sum(deductions.values()) == 1
    assert deductions[requests[1].id] == 1


def test_paid_pms_deduction_counts_half_day_after_partially_used_allowance():
    policy = SimpleNamespace(paid_leave_per_month=1.5)
    requests = [
        paid_request(start_date=date(2026, 8, 19), days=1),
        paid_request(start_date=date(2026, 8, 22), days=0.5, day_part='HALF'),
        paid_request(start_date=date(2026, 8, 23), days=0.5, day_part='HALF'),
    ]

    deductions = LeaveManagementService._paid_pms_deductions_by_request(None, policy, requests)

    assert sum(deductions.values()) == 1
    assert deductions[requests[2].id] == 1


def test_paid_pms_deduction_uses_request_order_not_leave_date_order():
    policy = SimpleNamespace(paid_leave_per_month=1.5)
    requests = [
        paid_request(
            start_date=date(2026, 8, 17),
            days=4,
            created_at=datetime(2026, 8, 10, tzinfo=UTC),
        ),
        paid_request(
            start_date=date(2026, 8, 15),
            days=0.5,
            day_part='HALF',
            created_at=datetime(2026, 8, 11, tzinfo=UTC),
        ),
        paid_request(
            start_date=date(2026, 8, 16),
            days=0.5,
            day_part='HALF',
            created_at=datetime(2026, 8, 12, tzinfo=UTC),
        ),
    ]

    deductions = LeaveManagementService._paid_pms_deductions_by_request(None, policy, requests)

    assert deductions[requests[0].id] == 3
    assert deductions[requests[1].id] == 1
    assert deductions[requests[2].id] == 1
    assert sum(deductions.values()) == 5


def test_paid_leave_duration_excludes_sundays():
    service = LeaveManagementService.__new__(LeaveManagementService)

    assert service._leave_days_excluding_sundays(date(2026, 8, 22), date(2026, 8, 24)) == 2
    assert service._leave_days_excluding_sundays(date(2026, 8, 23), date(2026, 8, 23)) == 0


def test_overlapping_leave_request_raises_clear_date_range_message():
    service = LeaveManagementService.__new__(LeaveManagementService)
    service.db = SimpleNamespace(
        scalar=lambda statement: SimpleNamespace(
            start_date=date(2026, 8, 19),
            end_date=date(2026, 8, 22),
        )
    )

    with pytest.raises(HTTPException) as exc:
        service._ensure_no_overlapping_request(uuid4(), date(2026, 8, 21), date(2026, 8, 25))

    assert exc.value.status_code == 422
    assert exc.value.detail == 'You already have a leave request overlapping these dates (19-22). Please select different dates.'
