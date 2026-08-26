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


def test_short_leave_accepts_frontend_early_exit_without_break_pattern():
    payload = LeaveRequestCreate(
        leave_type='SHORT',
        start_date=date(2026, 8, 25),
        short_leave_pattern='EARLY_EXIT_WITHOUT_BREAK',
    )

    assert payload.short_leave_pattern == 'EARLY_EXIT_WITHOUT_BREAK'
