from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.daily_reports.schemas import ReportTasksUpdate
from app.modules.daily_reports.service import DailyReportService, format_report


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


def test_automatic_counts_use_the_india_calendar_day():
    class FakeSession:
        def execute(self, query):
            self.params = query.compile().params
            return [('M2M', None), ('M2M', None), ('Stock query', None)]

    db = FakeSession()
    tasks = DailyReportService(db).automatic_tasks(uuid4(), date(2026, 10, 23))
    assert tasks == [{'name': 'M2M', 'quantity': 2}, {'name': 'Stock query', 'quantity': 1}]
    assert datetime(2026, 10, 22, 18, 30, tzinfo=UTC) in db.params.values()
    assert datetime(2026, 10, 23, 18, 30, tzinfo=UTC) in db.params.values()
