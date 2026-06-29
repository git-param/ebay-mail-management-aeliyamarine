from datetime import date

from app.services.message_report_service import MessageReportService


def test_report_date_bounds_are_inclusive_calendar_dates():
    start, end = MessageReportService.bounds(date(2026, 6, 1), date(2026, 6, 30))
    assert start.isoformat() == '2026-06-01T00:00:00+00:00'
    assert end.isoformat() == '2026-07-01T00:00:00+00:00'


def test_report_date_bounds_allow_open_range():
    assert MessageReportService.bounds(None, None) == (None, None)
