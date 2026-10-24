from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.modules.daily_task_entry.service import DailyEntryService
from app.modules.task_management.activity import count_main_task


def task(name, source_type, weight=10):
    return SimpleNamespace(id=uuid4(), name=name, source_type=source_type,
                           weight=weight, message_type_id=None)


def test_daily_entry_only_includes_tasks_done_on_that_date(monkeypatch):
    booking = task('Booking', 'MESSAGE_TYPE', 20)
    follow_up = task('Follow up', 'MANUAL', 10)
    other = task('Other', 'OTHER', 5)
    untouched = task('Not done', 'MANUAL', 15)
    monkeypatch.setattr('app.modules.daily_task_entry.service.active_main_tasks',
                        lambda db: [booking, follow_up, other, untouched])
    db = Mock()
    db.scalar.return_value = SimpleNamespace(copied_at=True, automatic_tasks=[
        {'task_id': str(booking.id), 'name': 'Booking', 'quantity': 3},
    ], additional_tasks=[
        {'task_id': str(follow_up.id), 'name': 'Follow up', 'quantity': 2},
        {'task_id': str(other.id), 'name': 'Other', 'quantity': 1, 'remarks': 'Inventory review'},
    ])

    items = DailyEntryService(db)._main_task_items(uuid4(), date(2026, 10, 24))

    assert [item['label'] for item in items] == ['Booking', 'Follow up', 'Other']
    assert [item['quantity'] for item in items] == [3, 2, 1]
    assert [item['max_score'] for item in items] == [20.0, 10.0, 5.0]
    assert items[-1]['remarks'] == 'Inventory review'
    assert all(item['status'] == 'ENTERED' for item in items)


def test_daily_entry_has_no_task_scores_before_report_is_copied(monkeypatch):
    booking = task('Booking', 'MESSAGE_TYPE')
    monkeypatch.setattr('app.modules.daily_task_entry.service.active_main_tasks', lambda db: [booking])
    db = Mock()
    db.scalar.return_value = SimpleNamespace(copied_at=None, automatic_tasks=[], additional_tasks=[])
    assert DailyEntryService(db)._main_task_items(uuid4(), date(2026, 10, 24)) == []


def test_main_task_scores_respect_configured_weights():
    items = [
        {'key': 'main_task:one', 'status': 'ENTERED', 'value': 20, 'max_score': 20},
        {'key': 'main_task:two', 'status': 'ENTERED', 'value': 0, 'max_score': 10},
    ]
    # Weighted tasks are 66.7%; SLA is 100%; final score is their average.
    assert DailyEntryService(Mock()).calculate_final(items, 20, 'NO_ERROR') == 83


def test_parent_message_type_counts_its_descendants():
    parent, child, grandchild = uuid4(), uuid4(), uuid4()
    db = Mock()
    db.scalars.side_effect = [[child], [grandchild], []]
    db.scalar.return_value = 4
    selected = SimpleNamespace(source_type='MESSAGE_TYPE', message_type_id=parent)

    assert count_main_task(db, selected, uuid4(), date(2026, 10, 24)) == 4
    count_query = db.scalar.call_args.args[0]
    values = count_query.compile().params.values()
    assert {parent, child, grandchild}.issubset(set().union(*(
        set(value) if isinstance(value, (list, tuple, set)) else {value} for value in values
    )))
