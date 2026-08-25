from datetime import UTC
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.models.conversation import ConversationNote
from app.repositories.conversation_repository import ConversationRepository
from app.services.conversation_note_service import ConversationNoteService


def test_conversation_search_includes_active_internal_notes():
    statement = ConversationRepository(None)._filtered_statement(search='warehouse escalation')

    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))

    assert 'conversation_notes' in sql
    assert 'conversation_notes.deleted_at IS NULL' in sql
    assert 'conversation_notes.body ILIKE' in sql


def test_update_note_rejects_deleted_or_mismatched_note(monkeypatch):
    conversation_id = uuid4()
    note_id = uuid4()
    service = ConversationNoteService.__new__(ConversationNoteService)
    service.db = SimpleNamespace()
    service.repository = SimpleNamespace(get_active_for_conversation=lambda **kwargs: None)

    monkeypatch.setattr(
        'app.services.conversation_note_service.ConversationService',
        lambda db: SimpleNamespace(get_conversation=lambda requested_id: SimpleNamespace(id=requested_id, provider_account_id=uuid4())),
    )

    with pytest.raises(HTTPException) as exc:
        service.update_note(conversation_id=conversation_id, note_id=note_id, editor_id=uuid4(), body='Updated')

    assert exc.value.status_code == 404


def test_delete_note_soft_deletes_and_audits(monkeypatch):
    conversation_id = uuid4()
    note = ConversationNote(id=uuid4(), conversation_id=conversation_id, author_id=uuid4(), body='Private note')
    audit_calls = []
    db = SimpleNamespace(flush=lambda: None, commit=lambda: None)
    service = ConversationNoteService.__new__(ConversationNoteService)
    service.db = db
    service.repository = SimpleNamespace(get_active_for_conversation=lambda **kwargs: note)

    monkeypatch.setattr(
        'app.services.conversation_note_service.ConversationService',
        lambda db: SimpleNamespace(get_conversation=lambda requested_id: SimpleNamespace(id=requested_id, provider_account_id=uuid4())),
    )
    monkeypatch.setattr(
        'app.services.conversation_note_service.AuditService',
        lambda db: SimpleNamespace(log=lambda **kwargs: audit_calls.append(kwargs)),
    )

    deleted_by = uuid4()
    service.delete_note(conversation_id=conversation_id, note_id=note.id, deleted_by=deleted_by)

    assert note.deleted_at is not None
    assert note.deleted_at.tzinfo == UTC
    assert note.deleted_by == deleted_by
    assert audit_calls[0]['action'] == 'INTERNAL_NOTE_DELETED'
    assert audit_calls[0]['entity_id'] == note.id
