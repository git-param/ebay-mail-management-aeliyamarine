from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.daily_reports.schemas import ReportTasksUpdate, ReviewedTask
from app.modules.daily_reports.service import DailyReportService, format_report
from app.modules.task_management.activity import day_bounds


def agent():
    return SimpleNamespace(id=uuid4(), role=SimpleNamespace(name='Support Agent'))


def test_report_text_keeps_message_counts_and_omits_one_for_manual_tasks():
    text = format_report(
        date(2026, 10, 23),
        [{'name': 'M2M', 'quantity': 11}, {'name': 'Stock query', 'quantity': 1}],
        [{'name': 'VIP Inquiry Follow Up', 'quantity': 1}, {'name': 'Offer Follow ups', 'quantity': 2}],
    )
    assert text == ('Work Report: 23-10-2026\n\nM2M - 11\nStock query\n'
                    'VIP Inquiry Follow Up\nOffer Follow ups - 2')


def test_task_names_are_cleaned_and_duplicates_are_rejected():
    with pytest.raises(ValidationError):
        ReportTasksUpdate(report_date=date(2026, 10, 23), tasks=[
            {'name': '  Follow   up ', 'quantity': 1},
            {'name': 'follow up', 'quantity': 2},
        ])


def test_previous_day_cannot_be_saved_even_by_report_owner(monkeypatch):
    monkeypatch.setattr('app.modules.daily_reports.service.report_day', lambda: date(2026, 10, 24))
    with pytest.raises(HTTPException) as caught:
        DailyReportService(None).save_today(agent(), date(2026, 10, 23), [])
    assert caught.value.status_code == 409


def test_agent_cannot_read_another_users_reports():
    with pytest.raises(HTTPException) as caught:
        DailyReportService(None).list_reports(
            agent(), date_from=None, date_to=None, user_id=uuid4(), limit=50, offset=0,
        )
    assert caught.value.status_code == 403


def test_automatic_counts_include_only_recorded_shared_tasks(monkeypatch):
    message_task = SimpleNamespace(id=uuid4(), name='Booking', source_type='MESSAGE_TYPE')
    manual_task = SimpleNamespace(id=uuid4(), name='Follow up', source_type='MANUAL')
    monkeypatch.setattr('app.modules.daily_reports.service.active_main_tasks', lambda db: [message_task, manual_task])
    monkeypatch.setattr('app.modules.daily_reports.service.count_main_task', lambda db, task, user_id, day: 2)
    tasks = DailyReportService(None).automatic_tasks(uuid4(), date(2026, 10, 23))
    assert tasks == [{'task_id': str(message_task.id), 'name': 'Booking', 'quantity': 2}]


def test_main_task_counts_use_the_india_calendar_day():
    assert day_bounds(date(2026, 10, 23)) == (
        datetime(2026, 10, 22, 18, 30, tzinfo=UTC),
        datetime(2026, 10, 23, 18, 30, tzinfo=UTC),
    )


def test_manual_tasks_use_catalog_name_and_other_requires_remarks(monkeypatch):
    manual = SimpleNamespace(id=uuid4(), name='Follow up', source_type='MANUAL')
    other = SimpleNamespace(id=uuid4(), name='Other', source_type='OTHER')
    monkeypatch.setattr('app.modules.daily_reports.service.active_main_tasks', lambda db: [manual, other])
    service = DailyReportService(None)
    tasks = [{'task_id': str(manual.id), 'name': 'Changed name', 'quantity': 2, 'remarks': None}]
    service._validate_additional(tasks, None)
    assert tasks[0]['name'] == 'Follow up'

    with pytest.raises(HTTPException) as caught:
        service._validate_additional([{'task_id': str(other.id), 'name': 'Other', 'quantity': 1, 'remarks': ''}], None)
    assert caught.value.status_code == 422


def test_copy_snapshot_omits_zero_tasks_and_uses_reviewed_quantities(monkeypatch):
    booking = SimpleNamespace(id=uuid4(), name='Booking', source_type='MESSAGE_TYPE', weight=10)
    follow_up = SimpleNamespace(id=uuid4(), name='Follow up', source_type='MANUAL', weight=5)
    other = SimpleNamespace(id=uuid4(), name='Other', source_type='OTHER', weight=4)
    monkeypatch.setattr('app.modules.daily_reports.service.active_main_tasks', lambda db: [booking, follow_up, other])
    reviewed = [
        ReviewedTask(task_id=booking.id, quantity=3),
        ReviewedTask(task_id=follow_up.id, quantity=0),
        ReviewedTask(task_id=other.id, quantity=1, remarks='Stock review'),
    ]
    automatic, additional = DailyReportService(None)._reviewed_tasks(reviewed)
    assert automatic == [{'task_id': str(booking.id), 'name': 'Booking', 'quantity': 3, 'weight': 10.0, 'source_type': 'MESSAGE_TYPE'}]
    assert additional == [{'task_id': str(other.id), 'name': 'Other', 'quantity': 1, 'weight': 4.0, 'source_type': 'OTHER', 'remarks': 'Stock review'}]
    assert format_report(date(2026, 10, 24), automatic, additional) == 'Work Report: 24-10-2026\n\nBooking - 3\nOther (Stock review)'

    with pytest.raises(HTTPException) as caught:
        DailyReportService(None)._reviewed_tasks(reviewed[:-1])
    assert caught.value.status_code == 422


def test_copy_saves_reviewed_snapshot_before_returning_report(monkeypatch):
    day = date(2026, 10, 24)
    monkeypatch.setattr('app.modules.daily_reports.service.report_day', lambda: day)
    booking = SimpleNamespace(id=uuid4(), name='Booking', source_type='MESSAGE_TYPE', weight=10)
    monkeypatch.setattr('app.modules.daily_reports.service.active_main_tasks', lambda db: [booking])
    user = agent()
    user.full_name = 'Agent'
    saved = SimpleNamespace(id=uuid4(), user_id=user.id, user=user, report_date=day,
                            automatic_tasks=[{'task_id': str(booking.id), 'name': 'Booking', 'quantity': 2}],
                            additional_tasks=[], report_text='Work Report: 24-10-2026\n\nBooking - 2', copied_at=datetime.now(UTC))
    from unittest.mock import Mock
    db = Mock()
    db.scalar.side_effect = [None, saved]

    result = DailyReportService(db).save_today(user, day, copied=True,
                                               reviewed=[ReviewedTask(task_id=booking.id, quantity=2)])

    assert result['automatic_tasks'][0]['quantity'] == 2
    assert saved.report_text in db.execute.call_args.args[0].compile().params.values()
    db.commit.assert_called_once()
