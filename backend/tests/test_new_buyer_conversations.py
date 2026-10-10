import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.api.v1.routes import conversations, new_buyer_conversations
from app.db.session import get_db
from app.models.conversation import ConversationStatus, Message, MessageSenderType
from app.models.ebay_account import EbayConnectionStatus
from app.modules.integrations.ebay.client.ebay_auth_client import EbayAuthClient
from app.modules.integrations.ebay.services.ebay_message_service import EbayMessageService
from app.services import ebay_reply_service as replies
from app.services import new_buyer_conversation_service as new_buyers


@pytest.mark.parametrize('environment, host', [
    ('PRODUCTION', 'api.ebay.com'),
    ('SANDBOX', 'api.sandbox.ebay.com'),
])
def test_first_message_uses_username_and_selected_environment(environment, host):
    client = EbayAuthClient(
        client_id='test', client_secret='test', redirect_uri='test',
        runame='test', environment=environment,
    )
    client._request_message_api_raw = Mock(return_value='sent')
    media = [{'mediaName': 'photo', 'mediaUrl': 'image-url'}]

    assert client.start_conversation_message(
        'selected-account-token', buyer_username='unknown-to-aces',
        message_body='Hello', message_media=media, email_copy_to_sender=False,
    ) == 'sent'

    args, kwargs = client._request_message_api_raw.call_args
    assert args == ('selected-account-token',)
    assert urlsplit(kwargs['request_url']).netloc == host
    assert urlsplit(kwargs['request_url']).path == '/commerce/message/v1/send_message'
    assert kwargs['payload'] == {
        'otherPartyUsername': 'unknown-to-aces', 'messageText': 'Hello',
        'messageMedia': media, 'emailCopyToSender': False,
    }


def new_buyer_fixture(monkeypatch, *, existing=None, failure=None):
    account = SimpleNamespace(
        id=uuid4(), is_active=True, connection_status=EbayConnectionStatus.CONNECTED,
        ebay_username='chosen-seller',
    )
    db = Mock()
    db.get.return_value = account
    db.scalar.return_value = existing
    reply_service = Mock()
    reply_service.prepare_sending_account.return_value = account
    reply_service.send_reply = AsyncMock(side_effect=failure, return_value='sent-message')
    monkeypatch.setattr(new_buyers, 'EbayReplyService', Mock(return_value=reply_service))
    service = new_buyers.NewBuyerConversationService(db)
    payload = {
        'account_id': account.id, 'buyer_username': '  buyer-outside-aces  ',
        'body': 'Hello', 'actor_id': uuid4(), 'message_type_id': uuid4(),
        'send_copy_to_email': False, 'attachments': [],
    }
    return service, db, account, reply_service, payload


def test_selected_account_environment_is_used_before_refreshing_its_token():
    service = replies.EbayReplyService.__new__(replies.EbayReplyService)
    account = SimpleNamespace(id=uuid4(), environment='SANDBOX')
    service._get_account = Mock(return_value=account)
    service.token_service = Mock()
    service.token_service.client.environment = 'PRODUCTION'

    def refresh(selected_account):
        assert selected_account is account
        assert service.token_service.client.environment == 'SANDBOX'
        return selected_account

    service._ensure_access_token = refresh
    assert service.prepare_sending_account(account.id) is account


def test_first_message_does_not_require_a_local_buyer(monkeypatch):
    service, db, account, reply_service, payload = new_buyer_fixture(monkeypatch)

    assert asyncio.run(service.send_first_message(**payload)) == 'sent-message'

    thread = db.add.call_args.args[0]
    assert thread.provider_account_id == account.id
    assert thread.buyer_identifier == 'buyer-outside-aces'
    assert thread.provider_conversation_id.startswith('new-buyer-')
    assert thread.status == ConversationStatus.OPEN
    reply_service.prepare_sending_account.assert_called_once_with(account.id)
    assert reply_service.send_reply.call_args.kwargs['send_copy_to_email'] is False
    db.rollback.assert_not_called()


def test_first_message_reuses_existing_thread_for_the_selected_account(monkeypatch):
    existing = SimpleNamespace(id=uuid4())
    service, db, account, reply_service, payload = new_buyer_fixture(monkeypatch, existing=existing)

    asyncio.run(service.send_first_message(**payload))

    db.add.assert_not_called()
    assert reply_service.send_reply.call_args.kwargs['conversation_id'] == existing.id
    query = str(db.scalar.call_args.args[0])
    assert 'conversations.provider_account_id =' in query
    assert account.id in db.scalar.call_args.args[0].compile().params.values()


@pytest.mark.parametrize('failure', [HTTPException(status_code=502, detail='Invalid buyer'), RuntimeError('Upload failed')])
def test_failed_first_message_rolls_back_the_transient_conversation(monkeypatch, failure):
    service, db, _, _, payload = new_buyer_fixture(monkeypatch, failure=failure)

    with pytest.raises(type(failure)):
        asyncio.run(service.send_first_message(**payload))

    db.rollback.assert_called_once()
    db.commit.assert_not_called()


@pytest.mark.parametrize('username', ['', '   ', 'buyer name', 'chosen-seller'])
def test_rejects_invalid_or_self_recipient(monkeypatch, username):
    service, db, _, reply_service, payload = new_buyer_fixture(monkeypatch)
    payload['buyer_username'] = username

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.send_first_message(**payload))

    assert exc.value.status_code == 422
    reply_service.send_reply.assert_not_called()
    db.add.assert_not_called()


@pytest.mark.parametrize('active, connection_status', [
    (False, EbayConnectionStatus.CONNECTED),
    (True, EbayConnectionStatus.DISCONNECTED),
])
def test_rejects_unavailable_sending_account(monkeypatch, active, connection_status):
    service, db, account, reply_service, payload = new_buyer_fixture(monkeypatch)
    account.is_active = active
    account.connection_status = connection_status

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.send_first_message(**payload))

    assert exc.value.status_code == 400
    reply_service.send_reply.assert_not_called()
    db.add.assert_not_called()


@pytest.mark.parametrize('provider_id', ['ebay-thread-123', None])
@pytest.mark.parametrize('listing_id', ['236988914323', None])
def test_successful_send_records_identity_and_prevents_restarting_sent_thread(monkeypatch, provider_id, listing_id):
    actor_id, account_id = uuid4(), uuid4()
    thread = SimpleNamespace(
        id=uuid4(), status=ConversationStatus.OPEN, provider='EBAY',
        provider_conversation_id='new-buyer-local-id', provider_conversation_type='FROM_MEMBERS',
        provider_account_id=account_id, buyer_identifier='buyer-outside-aces', raw_payload={},
        reference_id=listing_id, reference_type='LISTING' if listing_id else None,
    )
    selected_type = SimpleNamespace(id=uuid4(), name='Message', is_deleted=False, is_active=True, children=[])
    service = replies.EbayReplyService.__new__(replies.EbayReplyService)
    service.db = Mock()
    service.db.get.return_value = selected_type
    service.db.query.return_value.filter.return_value.first.return_value = None
    service.reply_policy = Mock(validate=Mock(return_value=[]))
    service.attachment_service = Mock()
    service.token_service = Mock()
    response = {'messageId': 'sent-message-id'}
    if provider_id:
        response['conversationId'] = provider_id
    service.token_service.client.start_conversation_message.return_value = SimpleNamespace(ok=True, payload=response)
    service._get_account = Mock(return_value=SimpleNamespace(
        id=account_id, ebay_username='chosen-seller', access_token='chosen-token',
    ))
    service._ensure_access_token = lambda account: account
    service._existing_provider_message = Mock(return_value=None)
    monkeypatch.setattr(replies, 'ConversationService', Mock(return_value=Mock(get_conversation=Mock(return_value=thread))))
    assignment = Mock()
    assignment.repository.get_current_assignment.return_value = None
    monkeypatch.setattr(replies, 'AssignmentService', Mock(return_value=assignment))
    for dependency in ('SLAService', 'MessageClassificationRepository', 'AuditService'):
        monkeypatch.setattr(replies, dependency, Mock())

    asyncio.run(service.send_reply(
        conversation_id=thread.id, body='Hello', actor_id=actor_id,
        message_type_id=selected_type.id, send_copy_to_email=False,
    ))

    service._get_account.assert_called_once_with(account_id)
    service.token_service.client.start_conversation_message.assert_called_once_with(
        'chosen-token', buyer_username='buyer-outside-aces', message_body='Hello',
        message_media=None, email_copy_to_sender=False,
        **({'listing_id': listing_id} if listing_id else {}),
    )
    service.token_service.client.send_conversation_message.assert_not_called()
    assert thread.raw_payload['first_message_sent']
    service.db.commit.assert_called_once()
    if provider_id:
        assert thread.provider_conversation_id == provider_id
        assert service._send_context(thread)['conversation_id'] == provider_id
    else:
        with pytest.raises(HTTPException) as exc:
            service._send_context(thread)
        assert exc.value.status_code == 409


def test_sync_reconciles_sent_thread_using_the_matching_outbound_message():
    service = EbayMessageService.__new__(EbayMessageService)
    service.provider = 'EBAY'
    service.db = Mock()
    service.conversation_repository = Mock()
    service.conversation_repository.get_by_provider_id.return_value = None
    thread = SimpleNamespace(
        provider_conversation_id='new-buyer-local-id',
        raw_payload={'first_message_sent': True},
        messages=[SimpleNamespace(provider_message_id='sent-message-id')],
    )
    service.db.scalars.return_value = [thread]
    account = SimpleNamespace(id=uuid4())

    service._reconcile_new_buyer_conversation(
        account, 'ebay-thread-123',
        {'buyer_identifier': 'buyer', 'provider_conversation_type': 'FROM_MEMBERS'},
        [{'messageId': 'sent-message-id'}],
    )

    assert thread.provider_conversation_id == 'ebay-thread-123'
    assert account.id in service.db.scalars.call_args.args[0].compile().params.values()
    service.db.flush.assert_called_once()


def test_sync_does_not_attach_an_unrelated_thread_for_the_same_buyer():
    service = EbayMessageService.__new__(EbayMessageService)
    service.provider = 'EBAY'
    service.db = Mock()
    service.conversation_repository = Mock()
    service.conversation_repository.get_by_provider_id.return_value = None
    thread = SimpleNamespace(
        provider_conversation_id='new-buyer-local-id', raw_payload={'first_message_sent': True},
        messages=[SimpleNamespace(provider_message_id='sent-message-id')],
    )
    service.db.scalars.return_value = [thread]

    service._reconcile_new_buyer_conversation(
        SimpleNamespace(id=uuid4()), 'unrelated-thread',
        {'buyer_identifier': 'buyer', 'provider_conversation_type': 'FROM_MEMBERS'},
        [{'messageId': 'different-message-id'}],
    )

    assert thread.provider_conversation_id == 'new-buyer-local-id'
    service.db.flush.assert_not_called()


def test_sync_reconciles_when_ebay_omitted_both_ids_in_the_send_response():
    service = EbayMessageService.__new__(EbayMessageService)
    service.provider = 'EBAY'
    service.db = Mock()
    service.conversation_repository = Mock()
    service.conversation_repository.get_by_provider_id.return_value = None
    sent_at = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)
    thread = SimpleNamespace(
        provider_conversation_id='new-buyer-local-id', raw_payload={'first_message_sent': True},
        messages=[Message(
            provider='EBAY', provider_message_id='local-reply-first-message',
            sender_type=MessageSenderType.AGENT, is_inbound=False, body='Hello buyer',
            sender_identifier='chosen-seller', recipient_identifier='buyer', sent_at=sent_at,
        )],
    )
    service.db.scalars.return_value = [thread]

    service._reconcile_new_buyer_conversation(
        SimpleNamespace(id=uuid4()), 'ebay-thread-123',
        {'buyer_identifier': 'buyer', 'provider_conversation_type': 'FROM_MEMBERS'},
        [{
            'messageId': 'ebay-message-123', 'messageBody': 'Hello buyer',
            'senderUsername': 'chosen-seller', 'recipientUsername': 'buyer',
            'createdDate': '2026-10-09T08:00:02Z',
        }],
    )

    assert thread.provider_conversation_id == 'ebay-thread-123'


def test_new_buyer_routes_validate_and_deliver_multipart_before_dynamic_routes(monkeypatch):
    app = FastAPI()
    app.include_router(new_buyer_conversations.router, prefix='/conversations')
    app.include_router(conversations.router, prefix='/conversations')
    actor = SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_db] = lambda: Mock()
    now = datetime.now(UTC)
    message = Message(
        id=uuid4(), conversation_id=uuid4(), provider='EBAY',
        provider_message_id='ebay-message-123', sender_type=MessageSenderType.AGENT,
        sender_identifier='chosen-seller', recipient_identifier='buyer',
        body='Hello', is_inbound=False, read_status=True, sent_at=now, created_at=now,
    )
    sender = Mock(send_first_message=AsyncMock(return_value=message))
    monkeypatch.setattr(new_buyer_conversations, 'NewBuyerConversationService', Mock(return_value=sender))
    client = TestClient(app)

    validation = client.post('/conversations/start/validate', json={'body': 'Hello'})
    assert validation.status_code == 200
    assert validation.json()['valid']

    account_id, message_type_id = uuid4(), uuid4()
    response = client.post('/conversations/start', data={
        'account_id': str(account_id), 'buyer_username': 'buyer',
        'body': 'Hello', 'message_type_id': str(message_type_id),
        'send_copy_to_email': 'false',
    }, files={'attachments': ('photo.png', b'image', 'image/png')})

    assert response.status_code == 200
    assert response.json()['conversation_id'] == str(message.conversation_id)
    sent = sender.send_first_message.call_args.kwargs
    assert sent['account_id'] == account_id
    assert sent['actor_id'] == actor.id
    assert sent['send_copy_to_email'] is False
    assert sent['attachments'][0].filename == 'photo.png'


def test_new_buyer_routes_require_authentication():
    app = FastAPI()
    app.include_router(new_buyer_conversations.router, prefix='/conversations')

    def unauthenticated():
        raise HTTPException(status_code=401, detail='Sign in required')

    app.dependency_overrides[get_current_user] = unauthenticated
    app.dependency_overrides[get_db] = lambda: Mock()
    client = TestClient(app)

    assert client.post('/conversations/start/validate', json={'body': 'Hello'}).status_code == 401
    assert client.post('/conversations/start', data={
        'account_id': str(uuid4()), 'buyer_username': 'buyer',
        'body': 'Hello', 'message_type_id': str(uuid4()),
    }).status_code == 401
