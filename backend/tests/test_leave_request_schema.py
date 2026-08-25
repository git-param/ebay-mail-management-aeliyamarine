from datetime import date

from app.modules.leave_management.schemas import LeaveRequestCreate


def test_leave_request_reason_can_be_omitted():
    payload = LeaveRequestCreate(
        leave_type='PAID',
        start_date=date(2026, 8, 25),
    )

    assert payload.reason == ''


def test_leave_request_reason_can_be_blank():
    payload = LeaveRequestCreate(
        leave_type='PAID',
        start_date=date(2026, 8, 25),
        reason='',
    )

    assert payload.reason == ''
