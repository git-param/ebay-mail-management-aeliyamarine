from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.api.v1.routes import conversations as routes
from app.api.v1.routes.conversations import is_not_read_conversation
from app.schemas.conversation import ConversationReadStateRequest, BulkConversationReadStateRequest
from app.repositories.conversation_repository import ConversationRepository
from app.services import conversation_read_state_service as read_states
from app.utils.conversation_read_state import READ_STATE_KEY, apply_read_state, read_state_override


def thread(inbound=True):
    return SimpleNamespace(
        id=uuid4(), raw_payload={'provider_field': 'preserved'}, unread_count=1,
        messages=[SimpleNamespace(
            id=uuid4(), sent_at=datetime.now(UTC), is_inbound=inbound, read_status=False,
        )],
    )


@pytest.mark.parametrize('inbound', [True, False])
def test_mark_unread_applies_even_to_a_replied_conversation(inbound):
    conversation = thread(inbound)
    apply_read_state(conversation, False)
    assert read_state_override(conversation) is False
    assert is_not_read_conversation(conversation)
    assert conversation.raw_payload['provider_field'] == 'preserved'


def test_mark_read_clears_inbound_indicators_and_survives_provider_read_status_changes():
    conversation = thread()
    apply_read_state(conversation, True)
    assert conversation.unread_count == 0
    assert conversation.messages[0].read_status
    conversation.messages[0].read_status = False
    conversation.unread_count = 1
    assert not is_not_read_conversation(conversation)


def test_new_inbound_message_expires_previous_manual_read_state():
    conversation = thread()
    apply_read_state(conversation, True)
    conversation.messages.append(SimpleNamespace(
        id=uuid4(), sent_at=datetime.now(UTC) + timedelta(seconds=1),
        is_inbound=True, read_status=False,
    ))
    assert read_state_override(conversation) is None
    assert is_not_read_conversation(conversation)


def test_sync_preserves_local_read_override_without_overwriting_provider_payload():
    conversation = thread()
    apply_read_state(conversation, False)
    repository = ConversationRepository(Mock())
    repository.get_by_provider_id = Mock(return_value=conversation)
    repository.upsert_by_provider_id('EBAY', 'thread-id', {'raw_payload': {'summary': 'fresh'}})
    assert conversation.raw_payload['summary'] == 'fresh'
    assert conversation.raw_payload[READ_STATE_KEY]['is_read'] is False


def test_bulk_read_updates_all_unique_selected_conversations_atomically(monkeypatch):
    conversations = [thread(), thread()]
    db = Mock()
    loader = Mock(get_conversation=Mock(side_effect=conversations))
    monkeypatch.setattr(read_states, 'ConversationService', Mock(return_value=loader))
    audit = Mock()
    monkeypatch.setattr(read_states, 'AuditService', Mock(return_value=audit))
    count = read_states.ConversationReadStateService(db).update(
        [conversations[0].id, conversations[1].id, conversations[0].id],
        is_read=True, actor_id=uuid4(),
    )
    assert count == 2
    assert all(not is_not_read_conversation(value) for value in conversations)
    assert audit.log.call_count == 2
    db.commit.assert_called_once()


def test_missing_bulk_conversation_does_not_partially_update_selection(monkeypatch):
    conversation = thread()
    db = Mock()
    loader = Mock(get_conversation=Mock(side_effect=[conversation, HTTPException(status_code=404)]))
    monkeypatch.setattr(read_states, 'ConversationService', Mock(return_value=loader))
    with pytest.raises(HTTPException):
        read_states.ConversationReadStateService(db).update(
            [conversation.id, uuid4()], is_read=True, actor_id=uuid4(),
        )
    assert READ_STATE_KEY not in conversation.raw_payload
    db.commit.assert_not_called()


def test_unread_filter_includes_current_override_and_latest_message_identity():
    query = ConversationRepository(Mock())._filtered_statement(unread_only=True)
    sql = str(query.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
    assert 'aces_read_state' in sql
    assert 'message_id' in sql
    assert 'CASE WHEN' in sql
    assert 'CAST' in sql


def test_single_and_bulk_routes_pass_the_authenticated_actor_to_the_read_state_service(monkeypatch):
    db, actor = Mock(), SimpleNamespace(id=uuid4())
    service = Mock()
    service.update.return_value = 1
    monkeypatch.setattr(routes, 'ConversationReadStateService', Mock(return_value=service))
    conversation_id = uuid4()
    result = routes.update_conversation_read_state(
        conversation_id, ConversationReadStateRequest(is_read=False), db, actor,
    )
    assert result.updated_count == 1
    service.update.assert_called_with([conversation_id], is_read=False, actor_id=actor.id)
    routes.update_bulk_conversation_read_state(
        BulkConversationReadStateRequest(conversation_ids=[conversation_id], is_read=True), db, actor,
    )
    service.update.assert_called_with([conversation_id], is_read=True, actor_id=actor.id)
