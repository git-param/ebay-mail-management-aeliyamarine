from datetime import date

import pytest
from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

import app.db.base  # noqa: F401 - register all ORM relationships
from app.db.base_class import Base
from app.models.role import Role
from app.models.user import User
from app.modules.daily_task_entry.models import DailyTaskEntry
from app.modules.daily_task_entry.schemas import DailyEntryCreate, DailyEntryUploadEntry
from app.modules.daily_task_entry.service import DailyEntryService
from app.modules.pms.model import PmsMonthlyRecord, PmsMonthlyStatus
from app.modules.pms.service import PmsService


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://')
    names = [
        'roles', 'users', 'daily_task_entries', 'daily_task_entry_history',
        'pms_metric_configs', 'pms_monthly_records', 'pms_monthly_metrics',
        'pms_employee_of_month_selections',
    ]
    tables = [Base.metadata.tables[name] for name in names]
    for table in tables:
        for column in table.columns:
            if isinstance(column.type, JSONB):
                monkeypatch.setattr(column, 'type', JSON())
    Base.metadata.create_all(engine, tables=tables)
    monkeypatch.setattr(DailyEntryService, '_require_admin', lambda *args: None)
    monkeypatch.setattr(PmsService, '_require_view_all', lambda *args: None)
    monkeypatch.setattr(PmsService, '_authorize_self_or_privileged', lambda *args: None)
    monkeypatch.setattr(PmsService, '_leave_metric_value', lambda self, key, uid, year, month, weight: (
        (weight - 1 if key == 'attendance' else weight, {'deduction': 1 if key == 'attendance' else 0})
        if key in {'attendance', 'punctuality'} else None
    ))
    monkeypatch.setattr(PmsService, 'get_target_achievement_percent', lambda *args: None)
    with Session(engine, autoflush=False) as session:
        role = Role(name='Support Agent')
        user = User(email='agent@example.com', full_name='Agent', password_hash='test', role=role)
        session.add(user)
        session.commit()
        monkeypatch.setattr(PmsService, '_eligible_users', lambda *args: [user])
        yield session, user
    engine.dispose()


def payload(user, day=date(2026, 8, 3), value=8, sla=16):
    return DailyEntryCreate(
        user_id=user.id, entry_date=day, day_type='WORKING_DAY',
        error_level='NO_ERROR', sla_score=sla,
        score_items=[{'key': 'task', 'label': 'Task', 'value': value, 'max_score': 10, 'status': 'DONE'}],
    )


def scores(record):
    return {m.metric_key: float(m.final_value) for m in record.metrics}


def test_daily_save_persists_partial_pms_without_manual_save(db):
    session, user = db
    DailyEntryService(session).save(user, payload(user))
    record = session.scalar(select(PmsMonthlyRecord))
    assert record.status == PmsMonthlyStatus.DRAFT
    assert scores(record) == {
        'target_achievement': 0, 'productivity': 8, 'quality': 8,
        'attendance': 4, 'punctuality': 5, 'competency': 0,
    }
    assert float(record.final_score) == 25
    assert float(record.maximum_score) == 100


def test_overview_backfills_old_entries_and_keeps_empty_month_zero(db):
    session, user = db
    session.add(DailyTaskEntry(
        user_id=user.id, entry_date=date(2026, 8, 3), sla_score=10,
        score_items=[{'value': 6, 'max_score': 10}],
    ))
    session.commit()
    pms = PmsService(session)
    periods = pms.get_available_monthly_periods(user)
    assert [(p['year'], p['month']) for p in periods] == [(2026, 8)]
    august = pms.get_monthly_table(user, 2026, 8)
    assert august.items[0].record_id is not None
    assert august.items[0].final_score == 20
    assert august.pending_count == 1
    september = pms.get_monthly_table(user, 2026, 9)
    assert september.items[0].record_id is None
    assert not september.items[0].final_score
    draft = pms.get_monthly_record(user, user.id, 2026, 9)
    assert draft.final_score == 0
    assert all(m.final_value == 0 for m in draft.metrics)


def test_edits_average_entries_preserve_manual_scores_and_overrides(db):
    session, user = db
    daily = DailyEntryService(session)
    daily.save(user, payload(user))
    record = session.scalar(select(PmsMonthlyRecord))
    metrics = {m.metric_key: m for m in record.metrics}
    metrics['target_achievement'].final_value = 40
    metrics['competency'].final_value = 3
    metrics['quality'].final_value = 7
    metrics['quality'].was_overridden = True
    record.status = PmsMonthlyStatus.COMPLETED
    session.commit()
    daily.save(user, payload(user, value=2, sla=4))
    daily.save(user, payload(user, day=date(2026, 8, 4), value=10, sla=20))
    session.refresh(record)
    assert scores(record)['productivity'] == 6
    assert scores(record)['quality'] == 7
    assert float(metrics['quality'].auto_value) == 6
    assert scores(record)['target_achievement'] == 40
    assert scores(record)['competency'] == 3
    assert record.status == PmsMonthlyStatus.COMPLETED
    assert float(record.final_score) == 65


def test_deleting_last_daily_entry_clears_automatic_scores(db):
    session, user = db
    daily = DailyEntryService(session)
    daily.save(user, payload(user))
    assert daily.delete_entries(user, date_from=date(2026, 8, 1), date_to=date(2026, 8, 31)) == 1
    record = session.scalar(select(PmsMonthlyRecord))
    assert float(record.final_score) == 0
    assert all(value == 0 for value in scores(record).values())


def test_bulk_upload_updates_each_month_and_keeps_transaction_atomic(db):
    session, user = db
    entries = [DailyEntryUploadEntry(**payload(user, day=day).model_dump()) for day in [date(2026, 8, 3), date(2026, 9, 3)]]
    results = DailyEntryService(session).upload(user, entries)
    assert all(result.success for result in results)
    records = list(session.scalars(select(PmsMonthlyRecord).order_by(PmsMonthlyRecord.month)))
    assert [r.month for r in records] == [8, 9]
    assert all(float(r.final_score) == 25 for r in records)


def test_automatic_sync_does_not_commit_daily_transaction_when_config_unseeded(db):
    session, user = db
    DailyEntryService(session)._save_one(user, payload(user))
    session.rollback()
    assert session.scalar(select(DailyTaskEntry)) is None
    assert session.scalar(select(PmsMonthlyRecord)) is None



def test_automatic_target_placeholder_does_not_supply_monthly_target_percent(db):
    session, user = db
    DailyEntryService(session).save(user, payload(user))
    assert PmsService(session)._infer_target_achievement_percent(2026, 8) is None
    record = session.scalar(select(PmsMonthlyRecord))
    target = next(m for m in record.metrics if m.metric_key == 'target_achievement')
    target.final_value = 39
    target.calc_meta = {'target_percent': 60}
    session.flush()
    assert PmsService(session)._infer_target_achievement_percent(2026, 8) == 60
