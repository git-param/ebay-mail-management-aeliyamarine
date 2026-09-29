from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.conversation import Conversation, ConversationCategoryHistory, Message
from app.models.role import Role
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.audit_presentation_service import AuditPresentationService
from app.services.daily_login_service import audit_date_bounds, record_daily_login
from app.services.conversation_service import ConversationService
from app.services.assignment_service import AssignmentService
from app.api.v1.routes.audit_logs import delete_audit_logs, serialize_audit_log
from app.schemas.audit import AuditLogDeleteRequest


class MemoryDb:
    def __init__(self, *records):
        self.records = {(type(row), row.id): row for row in records}
        self.added = []
        self.executed = []
        self.commits = 0

    def get(self, model, identifier):
        return self.records.get((model, identifier))

    def add(self, row):
        self.added.append(row)

    def execute(self, statement, params=None):
        self.executed.append((str(statement.compile(dialect=postgresql.dialect())), params))
        return SimpleNamespace(rowcount=7)

    def scalar(self, statement):
        return None

    def commit(self):
        self.commits += 1

    def refresh(self, row):
        pass


def records():
    actor = User(id=uuid4(), full_name='Jayesh Patel', email='jayesh@example.com', role=Role(name='Admin'), must_reset_password=False)
    previous = User(id=uuid4(), full_name='Asha', email='asha@example.invalid', role=Role(name='Agent'))
    target = User(id=uuid4(), full_name='Ravi', email='ravi@example.invalid', role=Role(name='Agent'), is_active=True)
    conversation = Conversation(id=uuid4(), provider='EBAY', provider_conversation_id='buyer-thread-123',
        subject='Terminal panel printer', buyer_identifier='buyer110')
    return actor, previous, target, conversation


def test_assignment_records_who_from_and_to_and_survives_renames(monkeypatch):
    actor, previous, target, conversation = records()
    db = MemoryDb(actor, previous, target, conversation)
    service = AssignmentService(db)
    service.repository = SimpleNamespace(get_current_assignment=lambda _: SimpleNamespace(assigned_to=previous.id),
        close_current_assignment=lambda _: None, add=db.add)
    monkeypatch.setattr(ConversationService, 'get_conversation', lambda *args: conversation)
    service.assign_conversation(conversation_id=conversation.id, assigned_to=target.id, assigned_by=actor.id)
    log = next(row for row in db.added if isinstance(row, AuditLog))
    assert 'Jayesh Patel assigned Conversation buyer-thread-123' in log.audit_metadata['description']
    assert 'from Asha to Ravi' in log.audit_metadata['description']
    assert log.audit_metadata['conversation_id'] == str(conversation.id)
    target.full_name = 'Renamed user'
    assert 'to Ravi' in AuditPresentationService(db).enrich(action=log.action, user_id=actor.id,
        entity_type=log.entity_type, entity_id=log.entity_id, metadata=log.audit_metadata)['description']
    assert db.commits == 1


def test_category_change_preserves_both_names_and_actor(monkeypatch):
    actor, _, _, conversation = records()
    old = Category(id=uuid4(), name='Order inquiry')
    new = Category(id=uuid4(), name='Returns')
    conversation.category_id = old.id
    db = MemoryDb(actor, conversation, old, new)
    service = ConversationService(db)
    monkeypatch.setattr(service, 'get_conversation', lambda _: conversation)
    service.update_category(conversation_id=conversation.id, category_id=new.id, changed_by=actor.id)
    log = next(row for row in db.added if isinstance(row, AuditLog))
    assert 'from Order inquiry to Returns' in log.audit_metadata['description']
    assert 'Jayesh Patel changed' in log.audit_metadata['description']
    assert any(isinstance(row, ConversationCategoryHistory) for row in db.added)


@pytest.mark.parametrize('action,verb', [('MESSAGE_REPLY_SENT', 'replied in'), ('INTERNAL_NOTE_CREATED', 'created an internal note in')])
def test_reply_and_note_identify_actor_and_conversation(action, verb):
    actor, _, _, conversation = records()
    db = MemoryDb(actor, conversation)
    log = AuditService(db).log(action=action, user_id=actor.id, entity_type='CONVERSATION', entity_id=conversation.id)
    assert f'Jayesh Patel {verb} Conversation buyer-thread-123' in log.audit_metadata['description']
    assert 'Terminal panel printer' in log.audit_metadata['resource_label']


def test_missing_legacy_references_do_not_show_uuid_as_a_user_name():
    actor, _, _, conversation = records()
    unavailable = uuid4()
    result = AuditPresentationService(MemoryDb(actor, conversation)).enrich(action='CONVERSATION_ASSIGNED',
        user_id=actor.id, entity_type='CONVERSATION', entity_id=conversation.id, metadata={'assigned_to': str(unavailable)})
    assert 'Unavailable record' in result['description']
    assert str(unavailable) not in result['description']
    assert 'Previous assignee was not recorded' in result['description']


def test_legacy_category_transition_recovers_saved_history():
    actor, _, _, conversation = records()
    old = Category(id=uuid4(), name='Orders')
    new = Category(id=uuid4(), name='Warranty')
    db = MemoryDb(actor, conversation, old, new)
    db.scalar = lambda _: SimpleNamespace(old_category_id=old.id)
    result = AuditPresentationService(db).enrich(action='MESSAGE_CATEGORY_CHANGED', user_id=actor.id,
        entity_type='CONVERSATION', entity_id=conversation.id, metadata={'category_id': str(new.id)},
        created_at=datetime.now(UTC))
    assert 'from Orders to Warranty' in result['description']


def test_legacy_reply_category_gets_its_conversation_from_message():
    from app.models.message_type import MessageType
    actor, _, _, conversation = records()
    message = Message(id=uuid4(), conversation_id=conversation.id)
    message_type = MessageType(id=uuid4(), name='Shipping inquiry')
    result = AuditPresentationService(MemoryDb(actor, conversation, message, message_type)).enrich(
        action='REPLY_CATEGORIZED', user_id=actor.id, entity_type='MESSAGE', entity_id=message.id,
        metadata={'message_type_id': str(message_type.id)})
    assert 'buyer-thread-123' in result['description'] and 'Shipping inquiry' in result['description']
    assert result['conversation_id'] == str(conversation.id)


def test_serializer_keeps_event_actor_after_user_is_deleted():
    actor, _, _, conversation = records()
    db = MemoryDb(actor, conversation)
    log = AuditService(db).log(action='MESSAGE_REPLY_SENT', user_id=actor.id,
        entity_type='CONVERSATION', entity_id=conversation.id)
    log.id = uuid4()
    log.created_at = datetime.now(UTC)
    log.user = None
    db.records.clear()
    result = serialize_audit_log(log, AuditPresentationService(db))
    assert result.actor_name == 'Jayesh Patel'
    assert result.conversation_id == conversation.id
    assert 'Terminal panel printer' in result.resource_label


def test_india_day_boundaries_are_inclusive_and_exclude_next_day():
    start, end = audit_date_bounds(date(2026, 9, 29), date(2026, 9, 29))
    assert start == datetime(2026, 9, 28, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 9, 29, 18, 30, tzinfo=UTC)
    with pytest.raises(HTTPException) as exc:
        audit_date_bounds(date(2026, 9, 30), date(2026, 9, 29))
    assert exc.value.status_code == 422


def test_cookie_login_is_once_per_day_and_does_not_expose_tokens():
    actor, *_ = records()
    db = MemoryDb(actor)
    assert record_daily_login(db, actor, now=datetime(2026, 9, 29, 18, 29, tzinfo=UTC))
    log = db.added[-1]
    assert log.audit_metadata['login_date'] == '2026-09-29'
    assert log.action == 'LOGIN_SUCCESS'
    assert 'first login of the day' in log.audit_metadata['description']
    assert 'pg_advisory_xact_lock' in db.executed[0][0]
    db.scalar = lambda _: log.id or uuid4()
    assert not record_daily_login(db, actor, now=datetime(2026, 9, 29, 18, 29, tzinfo=UTC))
    assert len(db.added) == 1
    db.scalar = lambda _: None
    assert record_daily_login(db, actor, now=datetime(2026, 9, 29, 18, 30, tzinfo=UTC))
    assert db.added[-1].audit_metadata['login_date'] == '2026-09-30'
    assert db.executed[0][1]['key'] != db.executed[-1][1]['key']
    assert all('token' not in key for key in log.audit_metadata)


def test_password_login_already_today_prevents_restored_login_duplicate():
    actor, *_ = records()
    db = MemoryDb(actor)
    db.scalar = lambda _: uuid4()
    assert not record_daily_login(db, actor)
    assert db.added == []


def test_delete_requires_confirmation_and_bounded_range_and_keeps_deletion_event():
    actor, *_ = records()
    db = MemoryDb(actor)
    payload = AuditLogDeleteRequest(date_from='2026-09-28', date_to='2026-09-29', confirmation='invalid')
    with pytest.raises(HTTPException):
        delete_audit_logs(payload, db, actor)
    assert db.executed == []
    payload.confirmation = 'DELETE AUDIT LOGS'
    assert delete_audit_logs(payload, db, actor) == {'deleted_count': 7}
    assert 'created_at >=' in db.executed[0][0] and 'created_at <' in db.executed[0][0]
    assert db.added[-1].action == 'AUDIT_LOGS_DELETED'
    assert 'Jayesh Patel deleted 7 audit logs' in db.added[-1].audit_metadata['description']
    assert db.commits == 1


def test_non_admin_cannot_preview_or_delete_logs():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.dependencies import get_current_user
    from app.api.v1.routes.audit_logs import router
    from app.db.session import get_db
    actor, *_ = records()
    actor.role = Role(name='Agent')
    db = MemoryDb(actor)
    app = FastAPI()
    app.include_router(router, prefix='/audit-logs')
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        assert client.get('/audit-logs/deletion-preview?date_from=2026-09-28&date_to=2026-09-29').status_code == 403
        assert client.request('DELETE', '/audit-logs', json={'date_from': '2026-09-28', 'date_to': '2026-09-29', 'confirmation': 'DELETE AUDIT LOGS'}).status_code == 403
    assert db.executed == [] and db.added == []


def test_session_restore_endpoint_records_first_daily_login_without_token_values():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.dependencies import get_current_user
    from app.api.v1.routes.auth import router
    from app.db.session import get_db
    actor, *_ = records()
    db = MemoryDb(actor)
    db.scalar = lambda _: (uuid4() if db.added else None)
    app = FastAPI()
    app.include_router(router, prefix='/auth')
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        first = client.get('/auth/me')
        assert first.status_code == 200
        assert not first.json().get('access_token') and not first.json().get('refresh_token')
        assert client.get('/auth/me').status_code == 200
    assert len(db.added) == 1 and db.added[0].action == 'LOGIN_SUCCESS'
