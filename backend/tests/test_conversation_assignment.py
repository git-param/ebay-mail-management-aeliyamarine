import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.routes import conversations as routes
from app.models.conversation import ConversationStatus
from app.schemas.conversation import AssignConversationRequest, ReplyConversationRequest
from app.services import assignment_service as assignments
from app.services import ebay_reply_service as replies


def test_any_user_can_reassign_another_users_conversation(monkeypatch):
    db = Mock()
    thread = SimpleNamespace(id=uuid4(), status=ConversationStatus.OPEN)
    actor = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name='Other'))
    target = uuid4()
    assignment_service = Mock()
    assignment_service.repository.get_current_assignment.return_value = SimpleNamespace(assigned_to=uuid4())
    monkeypatch.setattr(routes, 'ConversationService', Mock(return_value=Mock(get_conversation=Mock(return_value=thread))))
    monkeypatch.setattr(routes, 'AssignmentService', Mock(return_value=assignment_service))
    notification = Mock()
    monkeypatch.setattr(routes, 'create_assignment_notification', notification)
    monkeypatch.setattr(routes, 'serialize_assignment', lambda assignment: assignment)

    result = routes.assign_conversation(thread.id, AssignConversationRequest(assigned_to=target), db, actor)

    assignment_service.assign_conversation.assert_called_once_with(
        conversation_id=thread.id, assigned_to=target, assigned_by=actor.id,
    )
    assert result == assignment_service.assign_conversation.return_value
    notification.assert_called_once()


def test_reply_validation_allows_another_users_assignment(monkeypatch):
    thread = SimpleNamespace(provider_conversation_type='FROM_MEMBERS')
    monkeypatch.setattr(routes, 'ConversationService', Mock(return_value=Mock(get_conversation=Mock(return_value=thread))))
    monkeypatch.setattr(routes, 'EbayReplyService', Mock(return_value=Mock(validate_reply=Mock(return_value=[]))))
    result = routes.validate_reply(uuid4(), ReplyConversationRequest(body='Thank you'), Mock(), SimpleNamespace(id=uuid4()))
    assert result.valid


@pytest.mark.parametrize('owner, delivered', [('other', True), ('self', True), (None, True), ('other', False)])
def test_reply_transfers_existing_assignment_only_after_success(monkeypatch, owner, delivered):
    actor_id = uuid4()
    thread = SimpleNamespace(
        id=uuid4(), status=ConversationStatus.OPEN, provider='EBAY',
        provider_conversation_type='FROM_MEMBERS', provider_account_id=uuid4(), buyer_identifier='buyer',
    )
    selected_type = SimpleNamespace(id=uuid4(), name='Reply', is_deleted=False, is_active=True, children=[])
    service = replies.EbayReplyService.__new__(replies.EbayReplyService)
    service.db = Mock(get=Mock(return_value=selected_type))
    service.reply_policy = Mock(validate=Mock(return_value=[]))
    service.attachment_service = Mock()
    service.token_service = Mock()
    service.token_service.client.send_conversation_message.return_value = SimpleNamespace(ok=delivered, payload={'messageId': 'sent-123'})
    service._get_account = Mock(return_value=SimpleNamespace(id=thread.provider_account_id, ebay_username='seller', access_token='token'))
    service._ensure_access_token = lambda account: account
    service._send_context = Mock(return_value={
        'transport': 'conversation', 'call_name': 'send_conversation_message',
        'conversation_id': 'thread-123', 'conversation_type': 'FROM_MEMBERS',
    })
    service._existing_provider_message = Mock(return_value=None)
    assignment_service = Mock()
    assignment_service.repository.get_current_assignment.return_value = (
        SimpleNamespace(assigned_to=actor_id if owner == 'self' else uuid4()) if owner else None
    )
    monkeypatch.setattr(replies, 'ConversationService', Mock(return_value=Mock(get_conversation=Mock(return_value=thread))))
    monkeypatch.setattr(replies, 'AssignmentService', Mock(return_value=assignment_service))
    for dependency in ('SLAService', 'MessageClassificationRepository', 'AuditService'):
        monkeypatch.setattr(replies, dependency, Mock())

    send = service.send_reply(conversation_id=thread.id, body='Thank you', actor_id=actor_id, message_type_id=selected_type.id)
    if delivered:
        asyncio.run(send)
        service.db.commit.assert_called_once()
    else:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(send)
        assert exc.value.status_code == 502
        service.db.rollback.assert_called_once()
        service.db.commit.assert_not_called()
    if delivered and owner == 'other':
        assignment_service.assign_conversation.assert_called_once_with(
            conversation_id=thread.id, assigned_to=actor_id, assigned_by=actor_id, commit=False,
        )
    else:
        assignment_service.assign_conversation.assert_not_called()


def test_reply_assignment_preserves_history_without_committing(monkeypatch):
    db = Mock(get=Mock(return_value=SimpleNamespace(is_active=True)))
    service = assignments.AssignmentService(db)
    service.repository = Mock()
    previous = SimpleNamespace(assigned_to=uuid4())
    service.repository.get_current_assignment.return_value = previous
    monkeypatch.setattr(assignments, 'ConversationService', Mock())
    audit = Mock()
    monkeypatch.setattr(assignments, 'AuditService', Mock(return_value=audit))
    thread_id, actor_id = uuid4(), uuid4()

    result = service.assign_conversation(conversation_id=thread_id, assigned_to=actor_id, assigned_by=actor_id, commit=False)

    assert result.assigned_to == actor_id
    service.repository.close_current_assignment.assert_called_once_with(thread_id)
    service.repository.add.assert_called_once_with(result)
    assert audit.log.call_args.kwargs['metadata']['previous_assignee'] == str(previous.assigned_to)
    db.commit.assert_not_called()
    db.flush.assert_called_once()
